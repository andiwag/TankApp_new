# Generate secrets for private beta deployment (copy output to Northflank env vars).
python -c @"
import secrets
print('SECRET_KEY=' + secrets.token_urlsafe(32))
print('CRON_SECRET=' + secrets.token_urlsafe(32))
print('REGISTRATION_INVITE_CODE=' + secrets.token_urlsafe(12))
"@
