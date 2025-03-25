# config.py
ZOHO_ORG_ID = "60038600013"
ZOHO_CLIENT_ID = "1000.EQ66ZF5CU8YC5MT45RCOFGNE5BVQBK"
ZOHO_CLIENT_SECRET = "9a0f33a2d327203fa6c74f0efc04f1222b2e607f46"
# Initially obtained access token
ZOHO_ACCESS_TOKEN = "1000.'1000.c8651ccfb7e32dceac58a2e6882d469e.7b43f1cde86667ef474ac0253ee80f83', .d95744555128f6de793307de0b332f3e"
# Your stored refresh token (which you don't expect to change often)
ZOHO_REFRESH_TOKEN = "1000.95c0693346ebb09b3b1944efe2a5ee51.b7f75d16f573ab766522811bbbd8feb9"

# API endpoints
ZOHO_API_DOMAIN = "https://www.zohoapis.in"
BILLS_ENDPOINT = "https://www.zohoapis.in/books/v3/bills/2353408000000035041?organization_id=60038600013"
TOKEN_REFRESH_URL = "https://accounts.zoho.in/oauth/v2/token"

# Set the token expiry (in seconds); typically, it's 3600 seconds (1 hour)
ACCESS_TOKEN_LIFESPAN = 3600
