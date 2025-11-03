# Elfsight to HCP Lead Creation Webhook

Automated lead creation system that captures Elfsight form submissions from lutzplumbingsf.com and creates leads/jobs in Housecall Pro (HCP).

## Features

- **Smart Customer Matching**: Intelligent duplicate detection using phone, email, and name matching
- **Automatic Lead Creation**: Creates customers and jobs in HCP from form submissions
- **Address Management**: Parses addresses and creates new service addresses when needed
- **Duplicate Handling**: Configurable logic based on "New/Existing Customer" form field
- **Private Notes**: Adds detailed form submission info as private notes to jobs
- **Rate Limiting**: Built-in rate limiting to respect HCP API limits
- **Error Handling**: Comprehensive error handling and logging
- **Cloud Deployment**: Ready for Google Cloud Run deployment

## Architecture

```
Elfsight Form → Webhook → Customer Matcher → Lead Creator → HCP API
                    ↓
                 Logging & Notes
```

### Components

- **main.py**: Flask webhook endpoint
- **lead_creator.py**: Orchestrates lead creation workflow
- **customer_matcher.py**: Smart customer matching logic
- **hcp_client.py**: HCP API client with rate limiting
- **utils.py**: Phone normalization, address parsing, etc.
- **config.py**: Environment configuration management

## Matching Logic

The system uses intelligent matching to prevent duplicates:

### Exact Match
- **Criteria**: Phone AND email both match existing customer
- **Action**: Use existing customer, create new job

### Partial Match
- **Criteria**: Phone OR email matches (but not both)
- **If form says "Existing Customer"**: Use matched customer with warning note
- **If form says "New Customer"**: Create new customer with warning note for review

### No Match
- **Action**: Create new customer and job

### Address Handling
- Compares new address with existing addresses (80% similarity threshold)
- Creates new service address if significantly different
- Adds warning notes when addresses don't match

## Setup

### Prerequisites

- Python 3.12+
- HCP API key
- Google Cloud account (for Cloud Run deployment)

### Local Development

1. **Clone/navigate to the project**:
   ```bash
   cd /Users/gh1/dev/hcp/elfsight-webhook
   ```

2. **Create virtual environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env and add your HCP_API_KEY
   ```

5. **Run locally**:
   ```bash
   python main.py
   ```

   The service will start on `http://localhost:8080`

### Testing Locally

You can test the webhook locally using curl or Postman:

```bash
# Test endpoint with simplified format
curl -X POST http://localhost:8080/test \
  -H "Content-Type: application/json" \
  -d '{
    "name": "John Smith",
    "email": "john@example.com",
    "phone": "415-555-1234",
    "address": "123 Main St, San Francisco, CA 94102",
    "message": "Need bathroom remodel quote",
    "customer_type": "Existing Customer"
  }'
```

```bash
# Test with Elfsight format (complete lead form)
curl -X POST http://localhost:8080/webhook \
  -H "Content-Type: application/json" \
  -d '[
    {"id": "field1", "name": "First Name", "value": "Sarah", "type": "short_text"},
    {"id": "field2", "name": "Last Name", "value": "Johnson", "type": "short_text"},
    {"id": "field3", "name": "Email Address", "value": "sarah.johnson@example.com", "type": "email"},
    {"id": "field4", "name": "Phone Number", "value": "(415) 555-7777", "type": "phone"},
    {"id": "field5", "name": "Street Address", "value": "456 Oak Avenue", "type": "short_text"},
    {"id": "field6", "name": "City", "value": "San Francisco", "type": "short_text"},
    {"id": "field7", "name": "State", "value": "CA", "type": "short_text"},
    {"id": "field8", "name": "Postal/Zip Code", "value": "94115", "type": "short_text"},
    {"id": "field9", "name": "New or Existing Customer", "value": "Existing Customer", "type": "choice"},
    {"id": "field10", "name": "Preferred Method of Contact", "value": "Phone", "type": "choice"},
    {"id": "field11", "name": "SMS Consent", "value": true, "type": "checkbox"},
    {"id": "field12", "name": "Service Needed", "value": "Service or Repair", "type": "choice"},
    {"id": "field13", "name": "Service Details", "value": "Water Heater,Toilets or Bidets", "type": "multiple_choice"},
    {"id": "field14", "name": "Service Request Details", "value": "Water heater making strange noises and toilet running constantly", "type": "textarea"}
  ]'
```

## Deployment to Google Cloud Run

### Option 1: Manual Deployment

1. **Set your project ID**:
   ```bash
   export PROJECT_ID=your-gcp-project-id
   gcloud config set project $PROJECT_ID
   ```

2. **Build and deploy**:
   ```bash
   gcloud builds submit --config cloudbuild.yaml
   ```

3. **Set environment variables** (after deployment):
   ```bash
   gcloud run services update elfsight-webhook \
     --region us-west1 \
     --set-env-vars HCP_API_KEY=your_api_key_here
   ```

4. **Get the service URL**:
   ```bash
   gcloud run services describe elfsight-webhook \
     --region us-west1 \
     --format 'value(status.url)'
   ```

### Option 2: Using gcloud directly

```bash
# Build the image
gcloud builds submit --tag gcr.io/$PROJECT_ID/elfsight-webhook

# Deploy to Cloud Run
gcloud run deploy elfsight-webhook \
  --image gcr.io/$PROJECT_ID/elfsight-webhook \
  --region us-west1 \
  --platform managed \
  --allow-unauthenticated \
  --memory 512Mi \
  --set-env-vars HCP_API_KEY=your_api_key_here,LOG_LEVEL=INFO
```

### Setting Environment Variables in Cloud Run

```bash
gcloud run services update elfsight-webhook \
  --region us-west1 \
  --set-env-vars \
    HCP_API_KEY=your_api_key_here,\
    HCP_LEAD_SOURCE="Elfsight Website Form",\
    DEFAULT_AREA_CODE=415,\
    LOG_LEVEL=INFO
```

## Elfsight Configuration

1. **Log into Elfsight** and open your form widget
2. **Go to Edit > Integrations**
3. **Add Webhook**:
   - URL: `https://your-cloud-run-url.run.app/webhook`
   - Method: POST
4. **Save** and test with a form submission

### Required Form Fields

Your Elfsight form should include:

**Required Fields:**
- **First Name** (required)
- **Last Name** (required)
- **Email Address** (required)
- **Phone Number** (required)

**Recommended Fields:**
- **Street Address** (recommended for service location)
- **City** (recommended)
- **Postal/Zip Code** (recommended)
- **New or Existing Customer** (important for matching logic)
  - Options: "New Customer" or "Existing Customer"

**Lead-Specific Fields:**
- **Preferred Method of Contact** (Phone, Email, Text)
- **SMS Consent** (checkbox for notifications)
- **Service Needed** (New Installation, Service or Repair, Renovation or Remodel)
- **Service Details** (multi-select: Water Heater, Toilets, Garbage Disposal, etc.)
- **Service Request Details** (textarea for detailed description)

## API Endpoints

### `GET /`
Health check endpoint.

**Response**:
```json
{
  "service": "Elfsight to HCP Lead Creator",
  "status": "running",
  "version": "1.0.0"
}
```

### `GET /health`
Detailed health check for Cloud Run.

**Response**:
```json
{
  "status": "healthy"
}
```

### `POST /webhook`
Main webhook endpoint for Elfsight submissions.

**Expected Payload**: Elfsight format (array of field objects)

**Response**:
```json
{
  "success": true,
  "message": "Lead created successfully",
  "customer_id": "abc123",
  "job_id": "xyz789",
  "warnings": ["Optional warning messages"]
}
```

### `POST /test`
Test endpoint for manual testing (accepts simplified JSON).

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `HCP_API_KEY` | Yes | - | Your HCP API key |
| `HCP_BASE_URL` | No | `https://api.housecallpro.com` | HCP API base URL |
| `HCP_LEAD_SOURCE` | No | `Elfsight Website Form` | Lead source tag |
| `HCP_LEAD_TAG` | No | `Elfsight Lead` | Tag for leads |
| `DEFAULT_AREA_CODE` | No | `415` | Default area code for phone numbers |
| `LOG_LEVEL` | No | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `PORT` | No | `8080` | Server port |

## Logging

The service logs to stdout (captured by Cloud Run):

- **INFO**: Normal operations, lead creation events
- **WARNING**: Partial matches, missing data
- **ERROR**: API errors, failures
- **DEBUG**: Detailed request/response data

View logs in Cloud Run:
```bash
gcloud run logs read elfsight-webhook --region us-west1
```

## Monitoring

### Cloud Run Metrics

Monitor in Google Cloud Console:
- Request count
- Request latency
- Error rate
- Memory usage

### Custom Metrics

Key events logged:
- Form submissions received
- Customer matches (exact, partial, none)
- Customers created
- Jobs created
- Addresses added
- API errors

## Troubleshooting

### Common Issues

**Issue**: "Configuration error: HCP_API_KEY is required"
- **Solution**: Set the HCP_API_KEY environment variable in Cloud Run

**Issue**: "Invalid phone number format"
- **Solution**: Check that phone numbers include area code or DEFAULT_AREA_CODE is set

**Issue**: "Failed to create customer"
- **Solution**: Check HCP API logs, ensure API key has correct permissions

**Issue**: Rate limiting errors
- **Solution**: Increase API_RATE_LIMIT_DELAY (default is 2.0 seconds)

### Debug Mode

For detailed debugging, set `LOG_LEVEL=DEBUG`:

```bash
gcloud run services update elfsight-webhook \
  --region us-west1 \
  --set-env-vars LOG_LEVEL=DEBUG
```

## Best Practices

1. **Always use the /test endpoint** before going live with Elfsight
2. **Monitor logs** for the first few submissions to verify correct behavior
3. **Review partial match warnings** in HCP job notes
4. **Keep DEFAULT_AREA_CODE** updated if you serve multiple regions
5. **Use private notes** for sensitive information (they're private by default)

## Security

- API keys are stored as environment variables (not in code)
- Elfsight webhooks have no built-in authentication
- Consider using Cloud Run authentication if you need added security
- Private notes are only visible to HCP admins

## Support

For issues or questions:
1. Check the logs: `gcloud run logs read elfsight-webhook`
2. Review the troubleshooting section above
3. Check HCP API documentation at `/Users/gh1/dev/hcp/hcp-import-work/api-reference/`

## License

Internal use for Lutz Plumbing SF.
