"""
Airtable route handlers
"""
from flask import Blueprint, request, jsonify
from datetime import datetime
from utils.logger import get_logger
from services.airtable_service import airtable_service

logger = get_logger(__name__)

# Create blueprint
airtable_bp = Blueprint('airtable', __name__, url_prefix='/airtable')

@airtable_bp.route('/records', methods=['GET'])
def get_airtable_records():
    """Retrieve records from Airtable"""
    try:
        # Get query parameters
        max_records = request.args.get('max_records', type=int)
        formula = request.args.get('formula')
        
        # Get records from service
        records = airtable_service.get_records(max_records=max_records, formula=formula)
        
        return jsonify({
            'status': 'success',
            'records': records,
            'count': len(records)
        }), 200
        
    except Exception as e:
        logger.error(f"Error retrieving Airtable records: {e}")
        return jsonify({'error': f'Failed to retrieve records: {str(e)}'}), 500

@airtable_bp.route('/records', methods=['POST'])
def create_airtable_record():
    """Create a new record in Airtable"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        # Add timestamp if not provided
        if 'Timestamp' not in data:
            data['Timestamp'] = datetime.now().isoformat()
        
        # Create record using service
        record = airtable_service.create_record(data)
        
        if record:
            return jsonify({
                'status': 'success',
                'message': 'Record created successfully',
                'record': record
            }), 201
        else:
            return jsonify({'error': 'Failed to create record'}), 500
            
    except Exception as e:
        logger.error(f"Error creating Airtable record: {e}")
        return jsonify({'error': f'Failed to create record: {str(e)}'}), 500

@airtable_bp.route('/records/<record_id>', methods=['GET'])
def get_airtable_record(record_id):
    """Get a specific record from Airtable"""
    try:
        record = airtable_service.get_record(record_id)
        
        if record:
            return jsonify({
                'status': 'success',
                'record': record
            }), 200
        else:
            return jsonify({'error': 'Record not found'}), 404
            
    except Exception as e:
        logger.error(f"Error retrieving Airtable record {record_id}: {e}")
        return jsonify({'error': f'Failed to retrieve record: {str(e)}'}), 500

@airtable_bp.route('/records/<record_id>', methods=['PUT'])
def update_airtable_record(record_id):
    """Update an existing record in Airtable"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        # Update record using service
        record = airtable_service.update_record(record_id, data)
        
        if record:
            return jsonify({
                'status': 'success',
                'message': 'Record updated successfully',
                'record': record
            }), 200
        else:
            return jsonify({'error': 'Failed to update record'}), 500
            
    except Exception as e:
        logger.error(f"Error updating Airtable record {record_id}: {e}")
        return jsonify({'error': f'Failed to update record: {str(e)}'}), 500

@airtable_bp.route('/records/<record_id>', methods=['DELETE'])
def delete_airtable_record(record_id):
    """Delete a record from Airtable"""
    try:
        success = airtable_service.delete_record(record_id)
        
        if success:
            return jsonify({
                'status': 'success',
                'message': 'Record deleted successfully'
            }), 200
        else:
            return jsonify({'error': 'Failed to delete record'}), 500
            
    except Exception as e:
        logger.error(f"Error deleting Airtable record {record_id}: {e}")
        return jsonify({'error': f'Failed to delete record: {str(e)}'}), 500

@airtable_bp.route('/records/search', methods=['GET'])
def search_airtable_records():
    """Search records in Airtable"""
    try:
        field = request.args.get('field')
        value = request.args.get('value')
        
        if not field or not value:
            return jsonify({'error': 'Both field and value parameters are required'}), 400
        
        # Search records using service
        records = airtable_service.search_records(field, value)
        
        return jsonify({
            'status': 'success',
            'records': records,
            'count': len(records),
            'search_field': field,
            'search_value': value
        }), 200
        
    except Exception as e:
        logger.error(f"Error searching Airtable records: {e}")
        return jsonify({'error': f'Failed to search records: {str(e)}'}), 500

@airtable_bp.route('/records/batch', methods=['POST'])
def batch_create_airtable_records():
    """Create multiple records in batch"""
    try:
        data = request.get_json()
        if not data or not isinstance(data, list):
            return jsonify({'error': 'Data must be a list of records'}), 400
        
        # Create records in batch using service
        records = airtable_service.batch_create_records(data)
        
        return jsonify({
            'status': 'success',
            'message': f'Created {len(records)} records successfully',
            'records': records,
            'count': len(records)
        }), 201
        
    except Exception as e:
        logger.error(f"Error batch creating Airtable records: {e}")
        return jsonify({'error': f'Failed to create records: {str(e)}'}), 500 