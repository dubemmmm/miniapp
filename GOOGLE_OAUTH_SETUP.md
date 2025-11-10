# Google OAuth Setup Guide

## Step 1: Install Required Packages

```bash
pip install django-allauth
```

## Step 2: Google Cloud Console Setup

### Create OAuth 2.0 Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Navigate to **APIs & Services** > **Credentials**
4. Click **Create Credentials** > **OAuth client ID**
5. Configure the OAuth consent screen if prompted:
   - User Type: External
   - App name: Your Real Estate App
   - User support email: your-email@example.com
   - Developer contact information: your-email@example.com
6. Select **Web application** as application type
7. Add **Authorized redirect URIs**:
   ```
   http://localhost:8000/accounts/google/login/callback/
   http://127.0.0.1:8000/accounts/google/login/callback/
   https://yourdomain.com/accounts/google/login/callback/
   ```
8. Click **Create**
9. Copy your **Client ID** and **Client Secret**

## Step 3: Add to Environment Variables

Create or update your `.env` file:

```
GOOGLE_OAUTH_CLIENT_ID=your-client-id-here.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=your-client-secret-here
```

## Step 4: Django Admin Configuration

After running migrations and starting the server:

1. Go to Django Admin: `http://localhost:8000/admin/`
2. Navigate to **Sites** and ensure you have:
   - Domain: `localhost:8000` (for development)
   - Display name: Your App Name
3. Navigate to **Social Applications** > **Add Social Application**
   - Provider: Google
   - Name: Google OAuth
   - Client ID: (paste from Google Console)
   - Secret Key: (paste from Google Console)
   - Sites: Select your site and move it to "Chosen sites"
4. Click **Save**

## Step 5: Run Migrations

```bash
python manage.py migrate
```

## Step 6: Test the Integration

1. Start your development server: `python manage.py runserver`
2. Visit: `http://localhost:8000/register/` or `http://localhost:8000/employee-register/`
3. Click "Continue with Google"
4. Authenticate with your Google account

## Production Setup

For production, update:
- Authorized redirect URIs to use your production domain
- Site domain in Django admin
- Ensure HTTPS is enabled

## Troubleshooting

### Error: redirect_uri_mismatch
- Verify the redirect URI in Google Console matches exactly (including trailing slash)
- Check the Site domain in Django admin

### Error: Social account not found
- Ensure the Social Application is configured correctly in Django admin
- Verify Client ID and Secret are correct

### Users created via Google OAuth
- Employee users: Will need to set their role in admin after first login
- External users: Automatically created with default permissions
