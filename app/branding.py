"""Product branding constants."""

PRODUCT_NAME = "Tankly"
PRODUCT_DOMAIN = "tankly.at"
PRODUCT_URL = f"https://www.{PRODUCT_DOMAIN}"

DEFAULT_MAIL_FROM = f"noreply@{PRODUCT_DOMAIN}"
SESSION_COOKIE_DEFAULT = "tankly_session"
FLASH_COOKIE_DEFAULT = "tankly_flash"
CSRF_COOKIE_DEFAULT = "tankly_csrf"
REDIS_KEY_PREFIX = "tankly"
