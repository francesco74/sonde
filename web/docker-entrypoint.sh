#!/bin/sh

# Create env-config.js with environment variables
cat <<EOF > /usr/share/nginx/html/env-config.js
window.ENV_CONFIG = {
  REST_URL: "${REST_URL:-http://localhost:5000}",
};
EOF

echo "Environment configuration created:"
cat /usr/share/nginx/html/env-config.js

# Execute the CMD
exec nginx -g "daemon off;"