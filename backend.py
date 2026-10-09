import sys
import io

try:
    if sys.stdout is not None:
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True
        )
    if sys.stderr is not None:
        sys.stderr = io.TextIOWrapper(
            sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True
        )
except Exception:
    pass


from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import re
import struct
import subprocess
import json
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from werkzeug.utils import secure_filename
from rectpack import newPacker
from collections import defaultdict
from datetime import datetime, timedelta
import logging
import math
import time
import bcrypt
import jwt
from functools import wraps


# ============================================
# OPTIONAL LIBRARY DETECTION
# ============================================
print('📦 Loading libraries...')
try:
    import ezdxf
    EZDXF_AVAILABLE = True
    print('✅ ezdxf loaded')
except ImportError:
    EZDXF_AVAILABLE = False
    print('❌ ezdxf not installed')

try:
    import ifcopenshell
    IFCOPENSHELL_AVAILABLE = True
    print('✅ ifcopenshell loaded')
except ImportError:
    IFCOPENSHELL_AVAILABLE = False
    print('❌ ifcopenshell not installed')
    

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='frontend', static_url_path='')
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
CORS(app,
     resources={r"/api/*": {"origins": "*"}},
     supports_credentials=True,
     allow_headers=["Content-Type", "Authorization"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])


UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

PACKAGE_NAME = 'CutPro_v3.0.zip'

# ============================================
# MONGODB (persistent storage)
# ============================================
from mongo_config import users_col, history_col, skp_col


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            current_user = data['username']
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
        return f(current_user, *args, **kwargs)
    return decorated

@app.route('/api/auth/signup', methods=['POST', 'OPTIONS'])
def signup():
    if request.method == 'OPTIONS':
        return '', 200
    try:
        data = request.json
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        email = data.get('email', '').strip()

        if not username or not password:
            return jsonify({'error': 'Username and password required'}), 400
        if len(username) < 3:
            return jsonify({'error': 'Username must be at least 3 characters'}), 400
        if len(password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters'}), 400
        if users_col.find_one({'username': username}):
            return jsonify({'error': 'Username already exists'}), 400

        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        users_col.insert_one({
            'username': username,
            'password': hashed,
            'email': email,
            'created_at': datetime.now().isoformat()
        })

        token = jwt.encode({
            'username': username,
            'exp': datetime.utcnow() + timedelta(days=7)
        }, app.config['SECRET_KEY'], algorithm='HS256')

        return jsonify({
            'success': True, 'token': token, 'username': username,
            'message': 'Account created successfully!'
        })
    except Exception as e:
        logger.error(f"Signup error: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/auth/login', methods=['POST', 'OPTIONS'])
def login():
    if request.method == 'OPTIONS':
        return '', 200
    try:
        data = request.json
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()

        if not username or not password:
            return jsonify({'error': 'Username and password required'}), 400

        user = users_col.find_one({'username': username})
        if not user:
            return jsonify({'error': 'Invalid username or password'}), 401

        if not bcrypt.checkpw(password.encode('utf-8'), user['password']):
            return jsonify({'error': 'Invalid username or password'}), 401

        token = jwt.encode({
            'username': username,
            'exp': datetime.utcnow() + timedelta(days=7)
        }, app.config['SECRET_KEY'], algorithm='HS256')

        return jsonify({
            'success': True, 'token': token, 'username': username,
            'message': 'Login successful!'
        })
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/verify', methods=['GET'])
@token_required
def verify_token(current_user):
    return jsonify({'success': True, 'username': current_user, 'message': 'Token is valid'})


@app.route('/api/history', methods=['GET', 'OPTIONS'])
@token_required
def get_history(current_user):
    if request.method == 'OPTIONS':
        return '', 200
    try:
        entries = list(history_col.find(
            {'username': current_user},
            {'_id': 0}
        ).sort('timestamp', -1).limit(100))
        return jsonify({'success': True, 'history': entries})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/history', methods=['POST', 'OPTIONS'])
@token_required
def save_history(current_user):
    if request.method == 'OPTIONS':
        return '', 200
    try:
        data = request.json
        parts_data = data.get('parts', [])
        results = data.get('results', {})
        settings = data.get('settings', {})

        entry = {
            'id': str(int(time.time() * 1000)),
            'username': current_user,
            'timestamp': datetime.now().isoformat(),
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'settings': settings,
            'parts': parts_data,
            'results': results,
            'total_parts': len(parts_data),
            'sheets_needed': (results or {}).get('total_sheets', 0)
        }
        history_col.insert_one(entry)
        entry.pop('_id', None)

        # Keep only 100 newest per user
        old_ids = [doc['_id'] for doc in history_col.find(
            {'username': current_user}
        ).sort('timestamp', -1).skip(100)]
        if old_ids:
            history_col.delete_many({'_id': {'$in': old_ids}})

        return jsonify({'success': True, 'message': 'History saved', 'entry': entry})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/history/<entry_id>', methods=['DELETE', 'OPTIONS'])
@token_required
def delete_history_entry(current_user, entry_id):
    if request.method == 'OPTIONS':
        return '', 200
    try:
        history_col.delete_one({'username': current_user, 'id': entry_id})
        return jsonify({'success': True, 'message': 'History entry deleted'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/history/clear', methods=['POST', 'OPTIONS'])
@token_required
def clear_history(current_user):
    if request.method == 'OPTIONS':
        return '', 200
    try:
        history_col.delete_many({'username': current_user})
        return jsonify({'success': True, 'message': 'History cleared'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

        
def check_blender():
    try:
        result = subprocess.run(['blender', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(' Blender found!')
            return True
    except:
        pass
    print(' Blender not found')
    return False

BLENDER_AVAILABLE = check_blender()

@app.route('/')
def serve_index():
    return send_from_directory('frontend', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('frontend', path)

@app.route('/api/status')
def api_status():
    installed = getattr(sys, 'frozen', False)
    return jsonify({
        'status': 'online',
        'version': '3.0.0',
        'installed': installed,     # True when running as CutPro.exe
        'mode': 'installed' if installed else 'web',
        'timestamp': datetime.now().isoformat(),
        'server': 'CutList Optimizer Pro',
        'features': {
            'dxf_parsing': EZDXF_AVAILABLE,
            'ifc_parsing': IFCOPENSHELL_AVAILABLE,
            'blender_parsing': BLENDER_AVAILABLE,
            'pln_parsing': True, 'skp_parsing': True,
            'adaptive_sheet_sizing': True, '2d_bin_packing': True,
            'material_grouping': True, 'smart_panel_detection': True,
            'scrap_utilization': True, 'wall_floor_filtering': True,
            'duplicate_capping': True, 'user_authentication': True,
            'history_tracking': True,
            'veneer_edge_detection': True
        },
        'supported_formats': {
            'dxf': EZDXF_AVAILABLE, 'dwg': EZDXF_AVAILABLE,
            'ifc': IFCOPENSHELL_AVAILABLE, 'pln': True,
            'rvt': IFCOPENSHELL_AVAILABLE, 'blend': BLENDER_AVAILABLE,
            'skp': True, 'svg': True, 'txt': True, 'csv': True
        }
    })

@app.route('/api/download-cutpro', methods=['GET'])
def download_cutpro():
    """Redirects to the CutPro package hosted on GitHub Releases."""
    from flask import redirect
    GITHUB_RELEASE_URL = 'https://github.com/Biruke123/cutpro-optimizer/releases/download/v3.8.1/CutPro_v3.8.zip'
    print(f"📥 Download requested → redirecting to GitHub Releases")
    return redirect(GITHUB_RELEASE_URL, code=302)

# ============================================
# ADAPTIVE SHEET SIZING & PACKING
# ============================================

# ============================================
# ADAPTIVE SHEET SIZING & PACKING (v4 — MaxRects)
# ============================================

def find_optimal_sheet_size(part_width, part_height, kerf):
    w = part_width + kerf
    h = part_height + kerf
    standard_sheets = [
        (2440, 1220, '8×4 ft'), (3050, 1220, '10×4 ft'),
        (3660, 1220, '12×4 ft'), (2440, 1830, '8×6 ft'),
        (3660, 1830, '12×6 ft'), (4000, 2000, '13×6.5 ft'),
        (5000, 2000, '16×6.5 ft'), (6000, 2000, '20×6.5 ft'),
    ]
    for sheet_w, sheet_h, name in standard_sheets:
        if (w <= sheet_w and h <= sheet_h) or (w <= sheet_h and h <= sheet_w):
            return sheet_w, sheet_h, f'Standard ({name})'
    custom_w = math.ceil(w / 100) * 100 + 100
    custom_h = math.ceil(h / 100) * 100 + 100
    return custom_w, custom_h, f'Custom ({custom_w}×{custom_h} mm)'


class MaxRectsPacker:
    """
    MaxRects bin packer with Best Short Side Fit heuristic.
    Guarantees no overlaps because free rectangles are split on every placement.
    """

    def __init__(self, bin_w, bin_h, kerf, allow_rotation=True):
        self.bin_w = bin_w
        self.bin_h = bin_h
        self.kerf = kerf
        self.allow_rotation = allow_rotation
        # free rects: list of [x, y, w, h]
        self.free_rects = [[0, 0, bin_w, bin_h]]
        self.placements = []  # each: {x, y, w, h, rotated}

    def _fits(self, x, y, w, h):
        """Check if rect (x,y,w,h) fits inside any free rect."""
        for fx, fy, fw, fh in self.free_rects:
            if x >= fx and y >= fy and x + w <= fx + fw and y + h <= fy + fh:
                return True
        return False

    def _score_bssf(self, w, h):
        """
        Best Short Side Fit: find the free rect where the leftover
        on the shorter side is smallest. Returns (best_score, x, y, rotated) or None.
        """
        best_score = None
        best = None

        for fx, fy, fw, fh in self.free_rects:
            # --- Normal orientation ---
            if w <= fw and h <= fh:
                leftover_h = fw - w   # horizontal leftover
                leftover_v = fh - h   # vertical leftover
                short = min(leftover_h, leftover_v)
                long_ = max(leftover_h, leftover_v)
                score = (short, long_)
                if best_score is None or score < best_score:
                    best_score = score
                    best = (fx, fy, w, h, False)

            # --- Rotated orientation ---
            if self.allow_rotation and h <= fw and w <= fh:
                leftover_h = fw - h
                leftover_v = fh - w
                short = min(leftover_h, leftover_v)
                long_ = max(leftover_h, leftover_v)
                score = (short, long_)
                if best_score is None or score < best_score:
                    best_score = score
                    best = (fx, fy, h, w, True)

        return best

    def _split_free_rects(self, placed_x, placed_y, placed_w, placed_h):
        """Split every free rect that intersects the placed rect."""
        new_rects = []
        pw, ph = placed_w + self.kerf, placed_h + self.kerf  # include kerf

        for fx, fy, fw, fh in self.free_rects:
            # No overlap? keep as-is
            if (placed_x >= fx + fw or placed_x + pw <= fx or
                placed_y >= fy + fh or placed_y + ph <= fy):
                new_rects.append([fx, fy, fw, fh])
                continue

            # Overlap → split into up to 4 sub-rects
            # Left strip
            if placed_x > fx:
                new_rects.append([fx, fy, placed_x - fx, fh])
            # Right strip
            if placed_x + pw < fx + fw:
                new_rects.append([placed_x + pw, fy, fx + fw - (placed_x + pw), fh])
            # Top strip
            if placed_y > fy:
                new_rects.append([fx, fy, fw, placed_y - fy])
            # Bottom strip
            if placed_y + ph < fy + fh:
                new_rects.append([fx, placed_y + ph, fw, fy + fh - (placed_y + ph)])

        # Remove duplicates and tiny rects
        cleaned = []
        for r in new_rects:
            if r[2] <= 0 or r[3] <= 0:
                continue
            if r[2] < 1 or r[3] < 1:
                continue
            if r not in cleaned:
                cleaned.append(r)
        self.free_rects = cleaned

    def insert(self, w, h):
        """
        Try to insert a part. Returns placement dict or None if it doesn't fit.
        """
        best = self._score_bssf(w, h)
        if best is None:
            return None

        x, y, pw, ph, rotated = best

        # Record placement
        self.placements.append({
            'x': x, 'y': y,
            'w': pw, 'h': ph,
            'rotated': rotated
        })

        # Split free rects
        self._split_free_rects(x, y, pw, ph)
        return self.placements[-1]


def pack_with_adaptive_sheets(parts, default_width, default_height, kerf):
    """
    Pack parts using MaxRects. Each sheet is packed independently.
    Returns list of sheet dicts with parts that are GUARANTEED not to overlap.
    """
    if not parts:
        return []

    # Expand quantities
    all_parts = []
    for part in parts:
        for _ in range(int(part.get('qty', 1))):
            all_parts.append({
                'w': float(part['w']),
                'h': float(part['h']),
                'material': part.get('material', '18mm Birch Plywood'),
                'label': part.get('label', 'Part')
            })

    if not all_parts:
        return []

    # Sort: largest area first (better packing)
    all_parts.sort(key=lambda p: p['w'] * p['h'], reverse=True)

    results = []
    sheet_counter = 1
    max_sheets = 500

    while all_parts and sheet_counter <= max_sheets:
        packer = MaxRectsPacker(default_width, default_height, kerf, allow_rotation=True)

        placed_on_sheet = []
        leftover = []

        # First pass: try to place everything
        for part in all_parts:
            placement = packer.insert(part['w'], part['h'])
            if placement:
                placed_on_sheet.append({
                    'w': placement['w'],
                    'h': placement['h'],
                    'qty': 1,
                    'material': part['material'],
                    'label': part['label'],
                    'x': placement['x'],
                    'y': placement['y'],
                    'rotated': placement['rotated']
                })
            else:
                leftover.append(part)

        # Second pass: try to squeeze leftover parts (rotated) into remaining space
        still_leftover = []
        for part in leftover:
            # Try rotated
            placement = packer.insert(part['h'], part['w'])
            if placement:
                placed_on_sheet.append({
                    'w': placement['w'],
                    'h': placement['h'],
                    'qty': 1,
                    'material': part['material'],
                    'label': part['label'],
                    'x': placement['x'],
                    'y': placement['y'],
                    'rotated': True
                })
            else:
                still_leftover.append(part)

        if not placed_on_sheet:
            # Safety: if nothing fits, break to avoid infinite loop
            break

        used_area = sum(p['w'] * p['h'] for p in placed_on_sheet)
        sheet_area = default_width * default_height
        efficiency = min(100.0, (used_area / sheet_area) * 100) if sheet_area > 0 else 0

        results.append({
            'sheet_number': sheet_counter,
            'sheet_width': default_width,
            'sheet_height': default_height,
            'sheet_type': 'Standard',
            'material': placed_on_sheet[0]['material'] if placed_on_sheet else '18mm Birch Plywood',
            'parts': placed_on_sheet,
            'used_area': used_area,
            'waste_area': max(0, sheet_area - used_area),
            'waste_percentage': max(0, 100 - efficiency),
            'efficiency': efficiency
        })

        sheet_counter += 1
        all_parts = still_leftover

    return results


def analyze_scrap_utilization(sheets, sheet_width, sheet_height):
    """
    DISABLED: The old scrap-utilization moved parts between sheets after packing,
    which is what caused visible overlaps. Removed for accuracy.
    """
    return sheets

# ============================================
# VENEER CALCULATOR — WITH EDGE COLOR DETECTION
# ============================================

@app.route('/api/calculate-veneer', methods=['POST', 'OPTIONS'])
def calculate_veneer():
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        parts = data.get('parts', [])
        waste_factor = float(data.get('wasteFactor', 10)) / 100
        edging = data.get('edging', False)
        
        print("\n" + "=" * 60)
        print("🎨 VENEER CALCULATION")
        print("=" * 60)
        
        if not parts:
            return jsonify({'error': 'No parts to calculate'}), 400
        
        total_length_mm = 0
        material_lengths = {}
        veneer_parts_count = 0
        non_veneer_parts_count = 0
        
        for part in parts:
            qty = float(part.get('qty', 1))
            material = part.get('material', '18mm Birch Plywood')
            label = part.get('label', 'PART')
            
            # Read veneer fields — accept ANY value > 0
            veneer_length_mm = float(part.get('veneer_length_mm', 0))
            has_veneer = part.get('has_veneer', False)
            
            print(f"  {label}: has_veneer={has_veneer}, length={veneer_length_mm}mm")
            
            # If has_veneer is true but length is 0, calculate from part dimensions
            # Only count parts that explicitly have veneer length
            # No fallback — trust the frontend's veneer_length_mm
            
            if not has_veneer or veneer_length_mm <= 0:
                non_veneer_parts_count += int(qty)
                continue
            
            veneer_parts_count += int(qty)
            part_total_mm = veneer_length_mm * qty
            total_length_mm += part_total_mm
            
            if material not in material_lengths:
                material_lengths[material] = 0
            material_lengths[material] += part_total_mm
        
        # Convert to meters
        total_length_m = total_length_mm / 1000.0
        total_with_waste = total_length_m * (1 + waste_factor)
        
        if edging:
            total_with_waste *= 1.1
        
        veneer_needed_m = total_with_waste
        
        material_breakdown = []
        for material, length_mm in material_lengths.items():
            length_m = length_mm / 1000.0
            percent = (length_m / total_length_m) * 100 if total_length_m > 0 else 0
            material_breakdown.append({
                'material': material,
                'thickness': 18,
                'edge_length': round(length_m, 2),
                'percent': round(percent, 1)
            })
        
        print(f"\n Results:")
        print(f"  Veneer parts: {veneer_parts_count}")
        print(f"  Non-veneer:   {non_veneer_parts_count}")
        print(f"  Total length: {total_length_m:.2f}m")
        print(f"  With waste:   {total_with_waste:.2f}m")
        print("=" * 60 + "\n")
        
        return jsonify({
            'success': True,
            'total_edge_length': round(total_length_m, 2),
            'total_with_waste': round(total_with_waste, 2),
            'veneer_needed_m': round(veneer_needed_m, 2),
            'waste_percentage': waste_factor * 100,
            'edging': edging,
            'material_breakdown': material_breakdown,
            'veneer_parts_count': veneer_parts_count,
            'non_veneer_parts_count': non_veneer_parts_count
        })
        
    except Exception as e:
        logger.error(f"Veneer calculation error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# ============================================
# OPTIMIZE ENDPOINT
# ============================================

@app.route('/api/optimize', methods=['POST', 'OPTIONS'])
def optimize():
    if request.method == 'OPTIONS':
        return '', 200
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        parts = data.get('parts', [])
        sheet_width = float(data.get('sheetWidth', 2440))
        sheet_height = float(data.get('sheetHeight', 1220))
        kerf = float(data.get('kerf', 3))
        priority = data.get('priority', 'area')
        scrap_utilization = data.get('scrap_utilization', True)
        
        if not parts:
            return jsonify({'error': 'No parts to optimize'}), 400
        
        expanded_parts = []
        for part in parts:
            qty = part.get('qty', 1)
            for _ in range(int(qty)):
                expanded_parts.append({
                    'w': float(part.get('length', 0)),
                    'h': float(part.get('width', 0)),
                    'material': part.get('material', '18mm Birch Plywood'),
                    'label': part.get('label', 'Part')
                })
        
        valid_parts = [p for p in expanded_parts if p['w'] > 10 and p['h'] > 10]
        
        if not valid_parts:
            return jsonify({'error': 'No valid parts'}), 400
        
        parts_by_material = defaultdict(list)
        for part in valid_parts:
            parts_by_material[part['material']].append(part)
        
        results = {}
        total_sheets = 0
        total_area = 0
        total_waste = 0
        
        for material, material_parts in parts_by_material.items():
            if priority == 'area':
                material_parts.sort(key=lambda p: p['w'] * p['h'], reverse=True)
            
            sheets = pack_with_adaptive_sheets(material_parts, sheet_width, sheet_height, kerf)
            
            if scrap_utilization:
                sheets = analyze_scrap_utilization(sheets, sheet_width, sheet_height)
            
            total_part_area = sum(p['w'] * p['h'] for p in material_parts)
            used_area = sum(s.get('used_area', 0) for s in sheets if not s.get('is_scrap_note', False))
            sheet_area = sum(s.get('sheet_width', 0) * s.get('sheet_height', 0) for s in sheets if not s.get('is_scrap_note', False))
            
            results[material] = {
                'sheets': sheets,
                'total_parts': len(material_parts),
                'total_area': total_part_area / 1000000,
                'used_area': used_area / 1000000,
                'sheet_area': sheet_area / 1000000,
                'waste_percentage': ((sheet_area - used_area) / sheet_area) * 100 if sheet_area > 0 else 0,
                'efficiency': (used_area / sheet_area) * 100 if sheet_area > 0 else 0,
                'sheets_needed': len([s for s in sheets if not s.get('is_scrap_note', False)])
            }
            
            total_sheets += len([s for s in sheets if not s.get('is_scrap_note', False)])
            total_area += total_part_area
            total_waste += sheet_area - used_area
        
        summary = {
            'total_sheets': total_sheets,
            'total_parts': len(valid_parts),
            'total_area': total_area / 1000000,
            'total_waste': total_waste / 1000000,
            'materials': list(parts_by_material.keys())
        }
        
        return jsonify({
            'success': True,
            'summary': summary, 'details': results,
            'sheet_width': sheet_width, 'sheet_height': sheet_height,
            'kerf': kerf
        })
    except Exception as e:
        logger.error(f"Optimize error: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ============================================
# SKP PARSER
# ============================================

def parse_skp_file(file_path):
    """Parse SKP file — handles BOTH scattered and normal files"""
    try:
        with open(file_path, 'rb') as f:
            data = f.read()
        
        all_parts = []
        print("🔍 SMART PANEL DETECTION from SKP...")
        
        print("🔍 DEBUG: Searching for PART_ patterns...")
        
        pattern_with_dims = re.compile(rb'PART_\d+_[A-Za-z0-9_]+_\d+x\d+')
        matches_with_dims = pattern_with_dims.findall(data)
        print(f"   Format 1 (with dims): {len(matches_with_dims)} matches")
        
        pattern_no_dims = re.compile(rb'PART_\d+_[A-Za-z0-9_ ]+')
        matches_no_dims = pattern_no_dims.findall(data)
        print(f"   Format 2 (no dims): {len(matches_no_dims)} matches")
        
        print("   Sample matches:")
        for m in matches_with_dims[:10]:
            print(f"      → {m.decode('utf-8', errors='ignore')}")
        for m in matches_no_dims[:10]:
            print(f"      → {m.decode('utf-8', errors='ignore')}")
        
        is_scattered = False
        matches = []
        
        if len(matches_with_dims) > 0:
            is_scattered = True
            matches = matches_with_dims
            print(f" Detected SCATTERED file (WITH dimensions): {len(matches)} parts")
        elif len(matches_no_dims) > 3:
            is_scattered = True
            matches = matches_no_dims
            print(f" Detected SCATTERED file (WITHOUT dimensions): {len(matches)} parts")
        
        if is_scattered:
            print(" Parsing scattered file...")
            
            seen_parts = {}
            for match in matches:
                try:
                    name = match.decode('utf-8', errors='ignore').strip()
                    print(f"   Processing: {name}")
                    
                    parts_split = name.split('_')
                    
                    if len(parts_split) < 3:
                        continue
                    
                    width = 0
                    height = 0
                    has_dims = False
                    
                    if 'x' in parts_split[-1]:
                        try:
                            w_str, h_str = parts_split[-1].split('x')
                            width = float(w_str)
                            height = float(h_str)
                            has_dims = True
                        except:
                            pass
                    
                    if has_dims:
                        label = '_'.join(parts_split[2:-1])
                    else:
                        label = '_'.join(parts_split[2:])
                    
                    label = label.strip()
                    
                    label_upper = label.upper()
                    if 'SMALL_PART' in label_upper:
                        continue
                    if 'SOLID_PIECE' in label_upper:
                        continue
                    
                    if not has_dims:
                        continue
                    
                    if width < 150 or height < 150:
                        continue
                    if width > 3000 or height > 3000:
                        continue
                    
                    key = f"{round(width/5)*5}_{round(height/5)*5}_{label}"
                    
                    if key in seen_parts:
                        seen_parts[key]['qty'] += 1
                    else:
                        seen_parts[key] = {
                            'w': round(width / 5) * 5,
                            'h': round(height / 5) * 5,
                            'qty': 1,
                            'material': '18mm Birch Plywood',
                            'label': label.replace('_', ' ') if label else 'PART'
                        }
                except Exception as e:
                    continue
            
            result = list(seen_parts.values())
            print(f" Extracted {len(result)} unique parts after filtering")
            
            if not result:
                return {
                    'error': 'No usable parts found after filtering.',
                    'hint': 'The SketchUp plugin needs to add dimensions to part names.'
                }
            
            return {
                'parts': result,
                'total_parts': len(result),
                'source': 'scattered'
            }
        
        print(" Parsing normal SKP file...")
        
        num_pattern = re.compile(rb'[-+]?\d+\.?\d*')
        all_numbers = []
        for match in num_pattern.finditer(data[:2000000]):
            try:
                val = float(match.group())
                if 50 < val < 5000:
                    all_numbers.append(round(val, 1))
            except:
                pass
        
        from collections import Counter
        num_counter = Counter(all_numbers)
        
        file_name_lower = file_path.lower()
        default_material = '18mm Birch Plywood'
        if 'mdf' in file_name_lower:
            default_material = '12mm MDF'
        
        MIN_SIZE = 50
        MAX_SIZE = 2500
        common_dims = [d for d, c in num_counter.items() if c > 1 and MIN_SIZE < d < MAX_SIZE]
        common_dims.sort(reverse=True)
        
        used = set()
        panel_count = 0
        
        for i in range(len(common_dims)):
            if common_dims[i] in used:
                continue
            for j in range(i + 1, len(common_dims)):
                if common_dims[j] in used:
                    continue
                
                w = common_dims[i]
                h = common_dims[j]
                count = num_counter.get(common_dims[i], 1)
                
                if w < 150 or h < 150:
                    used.add(common_dims[i])
                    used.add(common_dims[j])
                    continue
                
                if MIN_SIZE < w < MAX_SIZE and MIN_SIZE < h < MAX_SIZE:
                    used.add(common_dims[i])
                    used.add(common_dims[j])
                    panel_count += 1
                    all_parts.append({
                        'w': w, 'h': h,
                        'qty': min(count, 20),
                        'material': default_material,
                        'label': f'Panel {panel_count}'
                    })
                    break
        
        combined = {}
        for p in all_parts:
            w_rounded = round(p['w'] / 5) * 5
            h_rounded = round(p['h'] / 5) * 5
            key = f"{w_rounded}_{h_rounded}"
            
            if key in combined:
                combined[key]['qty'] += p.get('qty', 1)
            else:
                combined[key] = {
                    'w': w_rounded, 'h': h_rounded,
                    'qty': p.get('qty', 1),
                    'material': p.get('material', default_material),
                    'label': f'Panel {len(combined)+1}'
                }
        
        filtered_parts = []
        for p in combined.values():
            w = p['w']
            h = p['h']
            if w < 150 or h < 150:
                continue
            if 30 < w < 2500 and 30 < h < 2500:
                filtered_parts.append(p)
        
        result = filtered_parts
        print(f" After filter: {len(result)} real panels")
        
        if not result:
            return {
                'error': 'No real cabinet panels found.',
                'hint': 'Use the CutPro Scatter plugin in SketchUp for best results.'
            }
        
        return {'parts': result, 'total_parts': len(result)}
        
    except Exception as e:
        print(f" SKP parsing error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {'error': f'SKP parsing error: {str(e)}'}

# ============================================
# DXF PARSER
# ============================================

def parse_dxf_file(file_path):
    if not EZDXF_AVAILABLE:
        return {'error': 'ezdxf not installed'}
    try:
        doc = ezdxf.readfile(file_path)
        modelspace = doc.modelspace()
        parts = []
        for entity in modelspace:
            if entity.dxftype() == 'LWPOLYLINE':
                points = list(entity.get_points())
                if len(points) >= 4:
                    xs = [p[0] for p in points]
                    ys = [p[1] for p in points]
                    w = max(xs) - min(xs)
                    h = max(ys) - min(ys)
                    if 100 < w < 2500 and 100 < h < 2500:
                        layer = entity.dxf.layer if hasattr(entity.dxf, 'layer') else 'Default'
                        parts.append({
                            'w': round(w, 1), 'h': round(h, 1),
                            'qty': 1, 'material': '18mm Birch Plywood',
                            'label': layer[:20] if layer else 'Part'
                        })
        combined = {}
        for p in parts:
            key = f"{p['w']}_{p['h']}_{p['material']}"
            if key in combined:
                combined[key]['qty'] += 1
            else:
                combined[key] = p
        return list(combined.values()) if combined else None
    except Exception as e:
        return {'error': f'DXF parsing error: {str(e)}'}

# ============================================
# IFC PARSER
# ============================================

def parse_ifc_file(file_path):
    if not IFCOPENSHELL_AVAILABLE:
        return {'error': 'ifcopenshell not installed'}
    try:
        ifc_file = ifcopenshell.open(file_path)
        parts = []
        elements = ifc_file.by_type('IfcBuildingElement')
        for element in elements:
            try:
                props = ifc_file.get_inverse(element)
                for prop in props:
                    if hasattr(prop, 'NominalWidth') and hasattr(prop, 'NominalLength'):
                        width = float(prop.NominalWidth) * 1000
                        height = float(prop.NominalLength) * 1000
                        if 100 < width < 2500 and 100 < height < 2500:
                            parts.append({
                                'w': round(width, 1), 'h': round(height, 1),
                                'qty': 1, 'material': '18mm Birch Plywood',
                                'label': element.is_a()[:20]
                            })
                            break
            except:
                continue
        return parts if parts else None
    except Exception as e:
        return {'error': f'IFC parsing error: {str(e)}'}

def parse_pln_file(file_path):
    try:
        parts = []
        try:
            with zipfile.ZipFile(file_path, 'r') as zip_file:
                for file_name in zip_file.namelist():
                    if file_name.endswith('.xml') or file_name.endswith('.txt'):
                        with zip_file.open(file_name) as f:
                            content = f.read().decode('utf-8', errors='ignore')[:200000]
                            dims = extract_dimensions_from_text(content)
                            parts.extend(dims)
        except zipfile.BadZipFile:
            pass
        combined = {}
        for p in parts:
            key = f"{p['w']}_{p['h']}"
            if key in combined:
                combined[key]['qty'] = min(combined[key]['qty'] + 1, 999)
            else:
                combined[key] = p
        return list(combined.values()) if combined else None
    except Exception as e:
        return {'error': f'PLN parsing error: {str(e)}'}

def extract_dimensions_from_text(text):
    parts = []
    pattern1 = re.findall(r'(\d+\.?\d*)\s*[xX*]\s*(\d+\.?\d*)', text)
    for w_str, h_str in pattern1:
        try:
            w = float(w_str)
            h = float(h_str)
            if w < 10:
                w *= 1000
                h *= 1000
            if 100 < w < 2500 and 100 < h < 2500:
                parts.append({
                    'w': round(w, 1), 'h': round(h, 1),
                    'qty': 1, 'material': '18mm Birch Plywood', 'label': 'Part'
                })
        except:
            pass
    return parts

def parse_blend_with_blender(file_path):
    if not BLENDER_AVAILABLE:
        return {'error': 'Blender not installed'}
    script_content = '''
import bpy
import json
bpy.ops.wm.open_mainfile(filepath="''' + file_path + '''")
parts = []
for obj in bpy.data.objects:
    if obj.type == 'MESH':
        bbox = obj.bound_box
        if bbox:
            x_coords = [v[0] for v in bbox]
            y_coords = [v[1] for v in bbox]
            z_coords = [v[2] for v in bbox]
            width = (max(x_coords) - min(x_coords)) * 1000
            height = (max(y_coords) - min(y_coords)) * 1000
            depth = (max(z_coords) - min(z_coords)) * 1000
            if depth < 100 and width > 100 and height > 100:
                parts.append({
                    'w': round(width, 1), 'h': round(height, 1), 'qty': 1,
                    'material': '18mm Birch Plywood', 'label': obj.name[:20]
                })
print(json.dumps(parts))
'''
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(script_content)
        script_path = f.name
    try:
        result = subprocess.run(
            ['blender', '--background', '--python', script_path],
            capture_output=True, text=True, timeout=30
        )
        output = result.stdout
        json_match = re.search(r'\[.*\]', output, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return {'error': 'No parts found'}
    except Exception as e:
        return {'error': f'Blender parsing error: {str(e)}'}
    finally:
        if os.path.exists(script_path):
            os.remove(script_path)

def parse_file(file_path, filename):
    ext = filename.split('.')[-1].lower()
    print(f"🔍 Parsing file: {filename} (extension: {ext})")
    if ext in ['dxf', 'dwg']:
        return parse_dxf_file(file_path)
    elif ext in ['ifc', 'rvt']:
        return parse_ifc_file(file_path)
    elif ext == 'pln':
        return parse_pln_file(file_path)
    elif ext == 'skp':
        return parse_skp_file(file_path)
    elif ext == 'blend':
        return parse_blend_with_blender(file_path)
    else:
        return {'error': f'Unsupported file format: {ext}'}

# ============================================
# PARSE FILE ENDPOINT
# ============================================

@app.route('/api/parse-file', methods=['POST', 'OPTIONS'])
def parse_file_endpoint():
    if request.method == 'OPTIONS':
        return '', 200
    
    print("\n" + "="*60)
    print(" FILE UPLOAD RECEIVED")
    print("="*60)
    
    if 'file' not in request.files:
        print(" No file in request")
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)
    
    print(f" Saved: {filename}")
    print(f" Size: {os.path.getsize(filepath)} bytes")
    
    try:
        result = parse_file(filepath, filename)
        
        if result is None:
            return jsonify({
                'success': True, 'parts': [], 'total_parts': 0,
                'file_type': filename.split('.')[-1].upper(),
                'message': 'No parts found'
            })
        
        if isinstance(result, dict) and 'error' in result:
            print(f" Parser error: {result['error']}")
            return jsonify(result), 400
        
        if isinstance(result, dict) and 'parts' in result:
            parts_data = result['parts']
            warning = result.get('warning', None)
        else:
            parts_data = result
            warning = None
        
        for p in parts_data:
            if 'label' not in p:
                p['label'] = 'Part'
            if 'material' not in p:
                p['material'] = '18mm Birch Plywood'
            if 'qty' not in p:
                p['qty'] = 1
            if 'veneer_sides' not in p:
                p['veneer_sides'] = 0
        
        print(f" SUCCESS: Found {len(parts_data)} parts")
        for p in parts_data[:10]:
            print(f"   {p['w']}×{p['h']} x{p['qty']} - {p['label']}")
        
        response = {
            'success': True,
            'parts': parts_data,
            'total_parts': len(parts_data),
            'file_type': filename.split('.')[-1].upper()
        }
        if warning:
            response['warning'] = warning
        return jsonify(response)
        
    except Exception as e:
        print(f" EXCEPTION: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)
        print("="*60 + "\n")

# ============================================
# DEBUG ENDPOINT
# ============================================

@app.route('/api/debug-skp', methods=['POST', 'OPTIONS'])
def debug_skp():
    if request.method == 'OPTIONS':
        return '', 200
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)
    
    try:
        with open(filepath, 'rb') as f:
            data = f.read()
        
        result = {
            'filename': filename,
            'file_size': len(data),
            'detected_patterns': {},
            'sample_text': []
        }
        
        pattern_with_dims = re.compile(rb'PART_\d+_[A-Za-z0-9_]+_\d+x\d+')
        matches_with_dims = pattern_with_dims.findall(data)
        result['detected_patterns']['with_dims'] = len(matches_with_dims)
        result['detected_patterns']['with_dims_samples'] = [m.decode('utf-8', errors='ignore') for m in matches_with_dims[:20]]
        
        pattern_no_dims = re.compile(rb'PART_\d+_[A-Za-z0-9_ ]+')
        matches_no_dims = pattern_no_dims.findall(data)
        result['detected_patterns']['no_dims'] = len(matches_no_dims)
        result['detected_patterns']['no_dims_samples'] = [m.decode('utf-8', errors='ignore') for m in matches_no_dims[:20]]
        
        text_pattern = re.compile(rb'[A-Za-z]{4,}')
        text_matches = text_pattern.findall(data[:100000])
        result['sample_text'] = list(set([m.decode('utf-8', errors='ignore') for m in text_matches[:50]]))
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)

# ============================================
# PARTS FROM SKETCHUP PLUGIN
# ============================================

# ============================================
# PERSISTENT STORAGE FOR SKETCHUP PARTS
# ============================================
PARTS_FILE = 'latest_sketchup_parts.json'

def load_parts_from_db():
    try:
        doc = skp_col.find_one({'id': 'latest'})
        return doc['parts'] if doc else []
    except Exception as e:
        print(f"⚠️ Could not load parts from MongoDB: {e}")
        return []

def save_parts_to_file(parts):
    try:
        skp_col.replace_one(
            {'id': 'latest'},
            {
                'id': 'latest',
                'parts': parts,
                'updated_at': datetime.now().isoformat()
            },
            upsert=True
        )
        print(f"💾 Saved {len(parts)} parts to MongoDB")
    except Exception as e:
        print(f"⚠️ Could not save parts: {e}")

# Initialize
latest_sketchup_parts = load_parts_from_db()
print(f"📂 Loaded {len(latest_sketchup_parts)} parts from MongoDB")




@app.route('/api/parts-from-sketchup', methods=['POST', 'OPTIONS'])
def parts_from_sketchup():
    """Receives parts directly from the SketchUp plugin"""
    global latest_sketchup_parts
    
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.json
        if not data or 'parts' not in data:
            return jsonify({'error': 'No parts data'}), 400
        
        parts = data['parts']
        
        print("\n" + "=" * 60)
        print(" PARTS RECEIVED FROM SKETCHUP PLUGIN")
        print("=" * 60)
        print(f" Total parts received: {len(parts)}")
        
        # Filter and clean parts
        cleaned = []
        skipped_tiny = 0
        skipped_wall = 0
        
        for p in parts:
            width = float(p.get('width', 0))
            height = float(p.get('height', 0))
            label = str(p.get('label', 'PART')).upper()
            
            # Filter truly tiny parts (< 30mm)
            if width < 30 or height < 30:
                skipped_tiny += 1
                continue
            
            # Filter true walls/floors (both > 3000mm)
            if width > 3000 and height > 3000:
                skipped_wall += 1
                continue
            
            #  VENEER FIELDS — Match plugin field names EXACTLY
                        #  VENEER FIELDS — Support BOTH field name conventions
            # Try multiple field names for compatibility
            veneer_edges_count = int(p.get('veneer_edges', p.get('veneer_edge_count', 0)))
            veneer_length_mm_value = float(p.get('veneer_length_mm', p.get('veneer_total_length_mm', 0)))
            has_veneer_flag = bool(p.get('has_veneer', veneer_edges_count > 0))
            
            cleaned.append({
                'width': width,
                'height': height,
                'depth': float(p.get('depth', 18)),
                'material': p.get('material', '18mm Birch Plywood'),
                'label': label.replace('_', ' '),
                'qty': int(p.get('qty', 1)),
                # Veneer fields
                'veneer_edges': veneer_edges_count,
                'veneer_length_mm': veneer_length_mm_value,
                'has_veneer': has_veneer_flag
            })
        
        print(f" After filtering: {len(cleaned)} valid parts")
        print(f"    Skipped tiny (<30mm): {skipped_tiny}")
        print(f"    Skipped walls (>3000mm): {skipped_wall}")
        
        #  Count veneer parts (using correct field names)
        veneer_count = 0
        total_veneer_length = 0
        for p in cleaned:
            if p['has_veneer']:
                veneer_count += 1
                total_veneer_length += p['veneer_length_mm'] * p['qty']
        
        print(f"    Veneer parts: {veneer_count}")
        print(f"    Veneer length: {(total_veneer_length / 1000):.2f} m")
        
        # Show first 10 parts
        for p in cleaned[:10]:
            v_tag = "" if p['has_veneer'] else "  "
            print(f"   {v_tag} {p['width']}×{p['height']} - {p['label']} (veneer: {p['veneer_length_mm']}mm)")
        
        # Save to global storage
        latest_sketchup_parts = cleaned
        
        return jsonify({
            'success': True,
            'parts': cleaned,
            'total_parts': len(cleaned),
            'source': 'sketchup_plugin',
            'veneer_parts_count': veneer_count,
            'total_veneer_length_mm': total_veneer_length,
            'skipped_tiny': skipped_tiny,
            'skipped_wall': skipped_wall
        })
        
    except Exception as e:
        logger.error(f"Parts from SketchUp error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/latest-sketchup-parts', methods=['GET', 'OPTIONS'])
def get_latest_sketchup_parts():
    """Returns the parts most recently sent by the SketchUp plugin"""
    global latest_sketchup_parts
    
    if request.method == 'OPTIONS':
        return '', 200
    
    return jsonify({
        'success': True,
        'parts': latest_sketchup_parts,
        'total_parts': len(latest_sketchup_parts),
        'has_parts': len(latest_sketchup_parts) > 0
    })

# ============================================
# RUN
# ============================================

if __name__ == '__main__':
    print('=' * 60)
    print('  CUTLIST OPTIMIZER PRO v3.0')
    print(' Server: http://localhost:5000')
    print(' Features:')
    print('   SKP Scattered File Support')
    print('   Adaptive Sheet Sizing')
    print('   Smart Panel Detection')
    print('   Scrap Utilization')
    print('   Veneer Calculator with Edge Detection')
    print('=' * 60)
    print(' Starting server...')
    app.run(debug=False, port=5000, host='0.0.0.0')