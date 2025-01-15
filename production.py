from flask import Flask, request, jsonify, session, redirect, url_for
from authlib.integrations.flask_client import OAuth
from flask_session import Session
import requests

app = Flask(__name__)

# Secret key for session encryption
app.secret_key = 'II_oeBJBFYsw9qEbidwCA7JUUXCVLm2kl_E5lM4gq4QGdHe3bmBotAf1RTjHm4ZE'
app.config['SESSION_TYPE'] = 'filesystem'

# Session initialization
Session(app)

# Auth0 Configuration
AUTH0_DOMAIN = 'dev-ia464fvkubykimt6.us.auth0.com'
CLIENT_ID = 'jkmCyqGQMcGY1VtJtwCgUK1cGH3nQbwn'
CLIENT_SECRET = 'II_oeBJBFYsw9qEbidwCA7JUUXCVLm2kl_E5lM4gq4QGdHe3bmBotAf1RTjHm4ZE'

# OAuth configuration
oauth = OAuth(app)
auth0 = oauth.register(
    'auth0',
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    api_base_url=f'https://{AUTH0_DOMAIN}',
    access_token_url=f'https://{AUTH0_DOMAIN}/oauth/token',
    authorize_url=f'https://{AUTH0_DOMAIN}/authorize',
    client_kwargs={
        'scope': 'openid profile email',
    },
)

@app.route('/')
def home():
    return 'Welcome! <a href="/login">Login</a>'

@app.route('/login')
def login():
    # Redirect to Auth0's authorization page
    return auth0.authorize_redirect(redirect_uri=url_for('callback', _external=True))

@app.route('/callback')
def callback():
    # Obtain the authorization code from the callback request
    auth_code = request.args.get('code')

    # Exchange the authorization code for tokens
    token_url = f'https://{AUTH0_DOMAIN}/oauth/token'
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    data = {
        'grant_type': 'authorization_code',
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'code': auth_code,
        'redirect_uri': url_for('callback', _external=True),
    }

    response = requests.post(token_url, data=data, headers=headers)
    response_data = response.json()

    # Store the access token and ID token in the session
    if 'access_token' in response_data:
        session['access_token'] = response_data['access_token']
        session['id_token'] = response_data.get('id_token')
        return redirect('/dashboard')
    else:
        return jsonify(response_data)

@app.route('/dashboard')
def dashboard():
    # Use the access token to access protected resources
    access_token = session.get('access_token')
    if not access_token:
        return redirect('/')
    
    # Example: Fetch user information from Auth0
    userinfo_url = f'https://{AUTH0_DOMAIN}/userinfo'
    headers = {'Authorization': f'Bearer {access_token}'}
    response = requests.get(userinfo_url, headers=headers)

    if response.status_code == 200:
        userinfo = response.json()
        return jsonify(userinfo)
    else:
        return 'Could not fetch user information', response.status_code

@app.route('/logout')
def logout():
    # Clear the session and redirect to Auth0's logout endpoint
    session.clear()
    logout_url = f'https://{AUTH0_DOMAIN}/v2/logout?client_id={CLIENT_ID}&returnTo={url_for("home", _external=True)}'
    return redirect(logout_url)

if __name__ == '__main__':
    app.run(debug=True)
