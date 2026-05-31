import time
from flask import Flask, jsonify, request, redirect, make_response
from authlib.jose import JsonWebKey, jwt

app = Flask(__name__)

# Einmaliger RSA-Schlüssel für die Signierung von Tokens generieren (wird von authlib benötigt)
private_key_dict = JsonWebKey.generate_key('RSA', 2048, is_private=True)
public_key_dict = private_key_dict.as_dict(is_private=False)

ISSUER = "http://localhost:3000"

@app.route('/.well-known/openid-configuration')
def openid_config():
    return jsonify({
        "issuer": ISSUER,
        "authorization_endpoint": f"{ISSUER}/iserv/oauth/v2/auth",
        "token_endpoint": f"{ISSUER}/iserv/oauth/v2/token",
        "userinfo_endpoint": f"{ISSUER}/iserv/public/oauth/userinfo",
        "jwks_uri": f"{ISSUER}/iserv/oauth/v2/jwks",
        "scopes_supported": ["openid", "profile", "email", "roles", "groups", "iserv:roles", "iserv:groups"],
        "response_types_supported": ["code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"]
    })

@app.route('/iserv/oauth/v2/jwks')
def jwks():
    return jsonify({"keys": [public_key_dict]})

@app.route('/iserv/oauth/v2/auth')
def auth():
    redirect_uri = request.args.get('redirect_uri')
    state = request.args.get('state')
    nonce = request.args.get('nonce', 'dummy_nonce')
    
    # Wir speichern den Nonce kurz in einem Cookie, um ihn beim Token-Endpoint abzurufen
    resp = make_response(redirect(f"{redirect_uri}?code=mock_code&state={state}"))
    resp.set_cookie('mock_nonce', nonce)
    return resp

@app.route('/iserv/oauth/v2/token', methods=['POST'])
def token():
    nonce = request.cookies.get('mock_nonce', 'dummy_nonce')
    now = int(time.time())
    
    client_id = request.form.get('client_id', 'multisystem-client')
    
    header = {'alg': 'RS256', 'kid': public_key_dict['kid']}
    payload = {
        'iss': ISSUER,
        'sub': '1234567890',
        'aud': client_id,
        'exp': now + 3600,
        'iat': now,
        'nonce': nonce
    }
    
    id_token = jwt.encode(header, payload, private_key_dict).decode('utf-8')
    
    return jsonify({
        "access_token": "mock_access_token",
        "token_type": "Bearer",
        "expires_in": 3600,
        "id_token": id_token
    })

@app.route('/iserv/public/oauth/userinfo')
def userinfo():
    # Wir simulieren hier den Lehrer "Herr Müller"
    return jsonify({
        "sub": "1234567890",
        "name": "Herr Müller",
        "email": "mueller@schule.de",
        "preferred_username": "mueller",
        "roles": [
            {
                "id": "role-lehrer",
                "name": "lehrer",
                "displayName": "Lehrer"
            }
        ],
        "groups": [
            {
                "id": "group-lehrer",
                "name": "lehrer"
            }
        ]
    })

if __name__ == '__main__':
    print("Mock IServ Server laeuft auf http://localhost:3000")
    print("Trage in deiner .env / im Setup-Wizard Folgendes ein:")
    print("ISERV_DOMAIN=http://localhost:3000")
    print("ISERV_CLIENT_ID=multisystem-client")
    print("ISERV_CLIENT_SECRET=egal")
    app.run(port=3000)
