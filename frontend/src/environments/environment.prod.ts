export const environment = {
  production: true,
  // Deployed: the API Gateway HTTP API URL (Terraform output `api_base_url`).
  // Replaced at build time or injected via a config.json fetched at runtime.
  apiBaseUrl: '__API_BASE_URL__',
};
