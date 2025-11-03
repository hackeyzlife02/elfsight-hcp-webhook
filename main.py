"""
Elfsight to HCP Lead Creation Webhook.

Flask application that receives Elfsight form submissions and creates
leads/jobs in Housecall Pro.
"""

import logging
import sys
from flask import Flask, request, jsonify
from lead_creator import LeadCreator
from config import Config

# Configure logging
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Initialize lead creator
lead_creator = LeadCreator()


@app.route("/", methods=["GET"])
def home():
    """Home endpoint - health check"""
    return jsonify({
        "service": "Elfsight to HCP Lead Creator",
        "status": "running",
        "version": "1.0.0"
    })


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint for Cloud Run"""
    # Check configuration
    is_valid, error = Config.validate()

    if not is_valid:
        logger.error(f"Configuration error: {error}")
        return jsonify({
            "status": "unhealthy",
            "error": error
        }), 500

    return jsonify({
        "status": "healthy"
    })


@app.route("/webhook", methods=["POST"])
def webhook():
    """
    Elfsight webhook endpoint.

    Receives form submissions from Elfsight and creates leads in HCP.

    Expected payload (Elfsight format):
    [
        {"id": "field1", "name": "Name", "value": "John Smith", "type": "short_text"},
        {"id": "field2", "name": "Email", "value": "john@example.com", "type": "email"},
        {"id": "field3", "name": "Phone", "value": "415-555-1234", "type": "phone"},
        {"id": "field4", "name": "Address", "value": "123 Main St, SF, CA 94102", "type": "text"},
        {"id": "field5", "name": "Message", "value": "I need help...", "type": "textarea"},
        {"id": "field6", "name": "Customer Type", "value": "New Customer", "type": "choice"}
    ]

    Returns:
        200: Success (with customer_id and job_id)
        400: Bad request (invalid payload)
        500: Server error
    """
    try:
        # Get payload
        payload = request.get_json(silent=True)

        if not payload:
            logger.warning("Received empty payload")
            return jsonify({
                "success": False,
                "error": "Empty payload"
            }), 400

        logger.info(f"Received webhook payload: {len(payload) if isinstance(payload, list) else 'dict'} fields")
        logger.debug(f"Payload: {payload}")

        # Parse payload
        form_data = lead_creator.parse_elfsight_payload(payload)

        # Validate required fields
        if not form_data.get("name") and not form_data.get("email") and not form_data.get("phone"):
            logger.warning("Missing required fields (name, email, or phone)")
            return jsonify({
                "success": False,
                "error": "Missing required fields: at least one of name, email, or phone is required"
            }), 400

        # Create lead
        result = lead_creator.create_lead(form_data)

        if result.success:
            logger.info(f"Lead created successfully: customer={result.customer_id}, job={result.job_id}")

            response_data = {
                "success": True,
                "message": result.message,
                "customer_id": result.customer_id,
                "job_id": result.job_id
            }

            if result.warnings:
                response_data["warnings"] = result.warnings

            return jsonify(response_data), 200

        else:
            logger.error(f"Failed to create lead: {result.error}")
            return jsonify({
                "success": False,
                "error": result.error
            }), 500

    except Exception as e:
        logger.exception(f"Unexpected error in webhook handler: {e}")
        return jsonify({
            "success": False,
            "error": "Internal server error"
        }), 500


@app.route("/test", methods=["POST"])
def test():
    """
    Test endpoint for manual testing.

    Accepts JSON in either Elfsight format or simplified format:
    {
        "name": "John Smith",
        "email": "john@example.com",
        "phone": "415-555-1234",
        "address": "123 Main St, San Francisco, CA 94102",
        "message": "I need plumbing help",
        "customer_type": "New Customer"
    }
    """
    try:
        payload = request.get_json(silent=True)

        if not payload:
            return jsonify({
                "success": False,
                "error": "Empty payload"
            }), 400

        logger.info("Test endpoint called")

        # Parse payload
        form_data = lead_creator.parse_elfsight_payload(payload)

        # Create lead
        result = lead_creator.create_lead(form_data)

        return jsonify(result.to_dict())

    except Exception as e:
        logger.exception(f"Error in test endpoint: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({
        "error": "Endpoint not found",
        "available_endpoints": ["/", "/health", "/webhook", "/test"]
    }), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"Internal server error: {error}")
    return jsonify({
        "error": "Internal server error"
    }), 500


if __name__ == "__main__":
    # Validate configuration on startup
    is_valid, error = Config.validate()
    if not is_valid:
        logger.error(f"Configuration error: {error}")
        sys.exit(1)

    logger.info("Starting Elfsight webhook service...")
    logger.info(f"Port: {Config.PORT}")
    logger.info(f"Log level: {Config.LOG_LEVEL}")

    # Run Flask app
    app.run(
        host="0.0.0.0",
        port=Config.PORT,
        debug=False  # Never use debug in production
    )
