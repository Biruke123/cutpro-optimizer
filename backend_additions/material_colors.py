"""
Material Colors system — added on top of existing backend.
This module gets imported into backend.py when we swap.
For now, we build it standalone in cutpro-next.
"""
from flask import Blueprint, request, jsonify
from datetime import datetime

# This will be set by the importing module
material_colors_col = None

def init(collection):
    """Called from backend.py to wire up the MongoDB collection."""
    global material_colors_col
    material_colors_col = collection

material_colors_bp = Blueprint('material_colors', __name__)

# ============================================
# DEFAULT PALETTE — 12 materials × 4 shades
# ============================================
DEFAULT_MATERIALS = [
    {
        "id": "oak", "name": "Oak",
        "shades": [
            {"label": "Base", "hex": "#BE805B"},
            {"label": "Light", "hex": "#D4A380"},
            {"label": "Dark", "hex": "#8A5A3B"},
            {"label": "Extra Light", "hex": "#EBCBAE"}
        ]
    },
    {
        "id": "walnut", "name": "Walnut",
        "shades": [
            {"label": "Base", "hex": "#6B3F23"},
            {"label": "Light", "hex": "#8A5636"},
            {"label": "Dark", "hex": "#452812"},
            {"label": "Extra Light", "hex": "#A87A5A"}
        ]
    },
    {
        "id": "teak", "name": "Teak",
        "shades": [
            {"label": "Base", "hex": "#A5762D"},
            {"label": "Light", "hex": "#C09455"},
            {"label": "Dark", "hex": "#78521A"},
            {"label": "Extra Light", "hex": "#D9B47F"}
        ]
    },
    {
        "id": "mahogany", "name": "Mahogany",
        "shades": [
            {"label": "Base", "hex": "#7B2D1F"},
            {"label": "Light", "hex": "#A44836"},
            {"label": "Dark", "hex": "#551A10"},
            {"label": "Extra Light", "hex": "#C87860"}
        ]
    },
    {
        "id": "cherry", "name": "Cherry",
        "shades": [
            {"label": "Base", "hex": "#9B4A2C"},
            {"label": "Light", "hex": "#B86B4A"},
            {"label": "Dark", "hex": "#6E3018"},
            {"label": "Extra Light", "hex": "#D18E6F"}
        ]
    },
    {
        "id": "pine", "name": "Pine",
        "shades": [
            {"label": "Base", "hex": "#E5C88C"},
            {"label": "Light", "hex": "#F0DAAF"},
            {"label": "Dark", "hex": "#B89A5E"},
            {"label": "Extra Light", "hex": "#F8ECD0"}
        ]
    },
    {
        "id": "birch", "name": "Birch",
        "shades": [
            {"label": "Base", "hex": "#D9C6A3"},
            {"label": "Light", "hex": "#E8DABD"},
            {"label": "Dark", "hex": "#A99B78"},
            {"label": "Extra Light", "hex": "#F5EBD8"}
        ]
    },
    {
        "id": "mdf", "name": "MDF",
        "shades": [
            {"label": "Base", "hex": "#C4A88E"},
            {"label": "Light", "hex": "#DDC7B0"},
            {"label": "Dark", "hex": "#8F7856"},
            {"label": "Extra Light", "hex": "#EFDFCD"}
        ]
    },
    {
        "id": "melamine", "name": "Melamine",
        "shades": [
            {"label": "Base", "hex": "#E8DCC4"},
            {"label": "Light", "hex": "#F2E9D6"},
            {"label": "Dark", "hex": "#B8AC95"},
            {"label": "Extra Light", "hex": "#F8F2E5"}

        ]
    },
    {
        "id": "plywood", "name": "Plywood",
        "shades": [
            {"label": "Base", "hex": "#C99A6E"},
            {"label": "Light", "hex": "#DEB791"},
            {"label": "Dark", "hex": "#9A7150"},
            {"label": "Extra Light", "hex": "#EED3B4"}
        ]
    },
    {
        "id": "bamboo", "name": "Bamboo",
        "shades": [
            {"label": "Base", "hex": "#D4B57A"},
            {"label": "Light", "hex": "#E5CD9C"},
            {"label": "Dark", "hex": "#A58B5B"},
            {"label": "Extra Light", "hex": "#F0E0BF"}
        ]
    },
    {
    "id": "uv_board", "name": "UV Board",
    "shades": [
        {"label": "Base", "hex": "#F8F9FA"},
        {"label": "Light", "hex": "#FCFCFD"},
        {"label": "Dark", "hex": "#E8EBEE"},
        {"label": "Extra Light", "hex": "#FFFFFF"}
    ]
},
    {
        "id": "mdf_gray", "name": "MDF Gray",
        "shades": [
            {"label": "Base", "hex": "#9E9E9E"},
            {"label": "Light", "hex": "#BEBEBE"},
            {"label": "Dark", "hex": "#6B6B6B"},
            {"label": "Extra Light", "hex": "#DDDDDD"}
        ]
    }
]

# ============================================
# ENDPOINTS
# ============================================

@material_colors_bp.route('/api/material-colors', methods=['GET', 'OPTIONS'])
def get_material_colors():
    if request.method == 'OPTIONS':
        return '', 200

    # If no auth, return defaults
    from flask import request as rq
    auth = rq.headers.get('Authorization', '')

    if not auth.startswith('Bearer '):
        return jsonify({'success': True, 'materials': DEFAULT_MATERIALS, 'source': 'default'})

    try:
        import jwt as pyjwt
        from flask import current_app
        token = auth.split(' ')[1]
        data = pyjwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
        username = data['username']
    except Exception:
        return jsonify({'success': True, 'materials': DEFAULT_MATERIALS, 'source': 'default'})

    if material_colors_col is None:
        return jsonify({'success': True, 'materials': DEFAULT_MATERIALS, 'source': 'default'})

    doc = material_colors_col.find_one({'username': username})
    if doc and 'materials' in doc:
        return jsonify({'success': True, 'materials': doc['materials'], 'source': 'user'})

    return jsonify({'success': True, 'materials': DEFAULT_MATERIALS, 'source': 'default'})


@material_colors_bp.route('/api/material-colors', methods=['POST', 'OPTIONS'])
def save_material_colors():
    if request.method == 'OPTIONS':
        return '', 200

    from flask import request as rq
    auth = rq.headers.get('Authorization', '')

    if not auth.startswith('Bearer '):
        return jsonify({'error': 'Authentication required'}), 401

    try:
        import jwt as pyjwt
        from flask import current_app
        token = auth.split(' ')[1]
        data = pyjwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
        username = data['username']
    except Exception:
        return jsonify({'error': 'Invalid token'}), 401

    if material_colors_col is None:
        return jsonify({'error': 'Storage unavailable'}), 500

    body = request.json or {}
    materials = body.get('materials', [])

    material_colors_col.update_one(
        {'username': username},
        {'$set': {
            'username': username,
            'materials': materials,
            'updated_at': datetime.now().isoformat()
        }},
        upsert=True
    )

    return jsonify({'success': True, 'message': 'Saved', 'count': len(materials)})


@material_colors_bp.route('/api/material-colors/reset', methods=['POST', 'OPTIONS'])
def reset_material_colors():
    if request.method == 'OPTIONS':
        return '', 200

    from flask import request as rq
    auth = rq.headers.get('Authorization', '')

    if not auth.startswith('Bearer '):
        return jsonify({'error': 'Authentication required'}), 401

    try:
        import jwt as pyjwt
        from flask import current_app
        token = auth.split(' ')[1]
        data = pyjwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
        username = data['username']
    except Exception:
        return jsonify({'error': 'Invalid token'}), 401

    if material_colors_col is not None:
        material_colors_col.delete_one({'username': username})

    return jsonify({'success': True, 'materials': DEFAULT_MATERIALS, 'message': 'Reset to defaults'})