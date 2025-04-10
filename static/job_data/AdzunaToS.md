# Adzuna API Terms of Service and Attribution

This application uses the Adzuna API to fetch job listings. By using this application, you agree to Adzuna's Terms of Service.

## Attribution

Job listing data provided by [Adzuna](https://www.adzuna.com/).

## Usage Restrictions

1. API calls are subject to rate limiting (maximum 20 calls per minute).
2. Job data retrieved from Adzuna is stored in a structured JSON format for caching purposes.
3. Data cached from Adzuna should be refreshed regularly to ensure accuracy.
4. The system is configured to respect Adzuna's terms of service by:
   - Maintaining proper attribution
   - Respecting rate limits
   - Using data in accordance with their terms

## API Access

To use the Adzuna integration, you need to obtain API credentials from [Adzuna's Developer Portal](https://developer.adzuna.com/).

1. Register for an Adzuna developer account
2. Create a new application to get your App ID and API Key
3. Set the environment variables:
   - `ADZUNA_APP_ID`
   - `ADZUNA_API_KEY`

## Legal

This application does not claim ownership of job data provided by Adzuna and acknowledges Adzuna as the source of all job listings.

For full terms of service, see the [Adzuna Terms](https://www.adzuna.com/terms-and-conditions) and [API Documentation](https://developer.adzuna.com/docs).