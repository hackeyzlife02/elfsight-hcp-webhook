# Quick Start Deployment Guide

## Step 1: Local Testing (5 minutes)

1. **Install dependencies**:
   ```bash
   cd /Users/gh1/dev/hcp/elfsight-webhook
   pip3 install -r requirements.txt
   ```

2. **Set environment variable**:
   ```bash
   export HCP_API_KEY="38642cf783b142e5988376c210d9175d"
   ```

3. **Run the service**:
   ```bash
   python3 main.py
   ```

4. **Test in another terminal**:
   ```bash
   curl -X POST http://localhost:8080/test \
     -H "Content-Type: application/json" \
     -d '{
       "name": "Test Customer",
       "email": "test@example.com",
       "phone": "555-1234",
       "address": "123 Main St, San Francisco, CA 94102",
       "message": "Test submission",
       "customer_type": "New Customer"
     }'
   ```

## Step 2: Deploy to Google Cloud Run (10 minutes)

1. **Set your project**:
   ```bash
   export PROJECT_ID=housecall-pro-455119
   gcloud config set project $PROJECT_ID
   ```

2. **Deploy**:
   ```bash
   cd /Users/gh1/dev/hcp/elfsight-webhook
   gcloud builds submit --config cloudbuild.yaml
   ```

3. **Set the HCP API key**:
   ```bash
   gcloud run services update elfsight-webhook \
     --region us-west1 \
     --set-env-vars HCP_API_KEY=38642cf783b142e5988376c210d9175d
   ```

4. **Get your webhook URL**:
   ```bash
   gcloud run services describe elfsight-webhook \
     --region us-west1 \
     --format 'value(status.url)'
   ```

   Save this URL - you'll need it for Elfsight!

## Step 3: Configure Elfsight (5 minutes)

1. **Log into Elfsight** and open your form on lutzplumbingsf.com

2. **Go to**: Edit > Integrations

3. **Add Webhook**:
   - **URL**: `https://your-cloud-run-url/webhook` (from step 2.4)
   - **Method**: POST
   - **Save**

4. **Test the form** on your website and check:
   - Cloud Run logs: `gcloud run logs read elfsight-webhook --region us-west1`
   - HCP for new customer/job

## Step 4: Verify in HCP (2 minutes)

After submitting a test form:

1. **Check logs**:
   ```bash
   gcloud run logs read elfsight-webhook \
     --region us-west1 \
     --limit 50
   ```

2. **Look for**:
   - "Lead created successfully"
   - Customer ID and Job ID in response

3. **In HCP**:
   - Find the new customer/job
   - Check the private note for form details
   - Verify tags: "Elfsight Lead", "Website"

## Important Form Configuration

Make sure your Elfsight form has these fields:

- **Name** (field name should contain "name")
- **Email** (field name should contain "email")
- **Phone** (field name should contain "phone")
- **Address** (field name should contain "address") - optional but recommended
- **Message** (field name should contain "message" or "comment")
- **Customer Type** (field name should contain "customer" and "type")
  - Options: "New Customer" or "Existing Customer"

## Troubleshooting

### Test isn't working locally?
```bash
# Check if service is running
curl http://localhost:8080/health

# Check environment variable
echo $HCP_API_KEY
```

### Deployment failed?
```bash
# Check Cloud Build logs
gcloud builds list --limit 5

# Check specific build
gcloud builds log [BUILD_ID]
```

### Webhook not receiving data?
1. Check Cloud Run logs for incoming requests
2. Verify Elfsight webhook URL is correct
3. Test with curl to isolate the issue:
   ```bash
   curl -X POST https://your-cloud-run-url/webhook \
     -H "Content-Type: application/json" \
     -d '[{"name":"Name","value":"Test"}]'
   ```

### Customer not being created?
1. Check Cloud Run logs for errors
2. Verify HCP_API_KEY has correct permissions
3. Test HCP API directly:
   ```bash
   curl -X GET https://api.housecallpro.com/v1/customers \
     -H "Authorization: Bearer 38642cf783b142e5988376c210d9175d"
   ```

## Monitoring

View real-time logs:
```bash
gcloud run logs tail elfsight-webhook --region us-west1
```

## Need Help?

1. Check README.md for detailed documentation
2. Review Cloud Run logs
3. Check HCP API documentation in `/Users/gh1/dev/hcp/hcp-import-work/api-reference/`
