#!/usr/bin/env python3
"""
Trigger script for role reassignment
Called by Node.js when reviewer or head_of_sales roles change
"""

import asyncio
import sys
import json
from logger import logger


async def main():
    """Main entry point for role reassignment"""
    try:
        # Read JSON payload from stdin
        input_data = sys.stdin.read()
        payload = json.loads(input_data)

        role_type = payload.get('role_type')
        old_user_id = payload.get('old_user_id')
        old_channel_id = payload.get('old_channel_id')
        new_user_id = payload.get('new_user_id')
        new_channel_id = payload.get('new_channel_id')

        if not all([role_type, old_user_id, old_channel_id, new_user_id, new_channel_id]):
            result = {
                'success': False,
                'error': 'Missing required parameters'
            }
            print(json.dumps(result))
            sys.exit(1)

        # Import role change handler
        from role_change_handler import reassign_reviewer_approvals, reassign_hos_approvals

        logger.info(f"🔄 Starting role reassignment for {role_type}")
        logger.info(f"   Old: {old_user_id} ({old_channel_id})")
        logger.info(f"   New: {new_user_id} ({new_channel_id})")

        # Trigger appropriate reassignment
        if role_type == 'reviewer':
            result = await reassign_reviewer_approvals(
                old_user_id, old_channel_id,
                new_user_id, new_channel_id
            )
        elif role_type == 'head_of_sales':
            result = await reassign_hos_approvals(
                old_user_id, old_channel_id,
                new_user_id, new_channel_id
            )
        else:
            result = {
                'success': False,
                'error': f'Invalid role type: {role_type}'
            }

        # Add success flag if not present
        if 'success' not in result:
            result['success'] = result.get('reassigned', 0) > 0 or result.get('total', 0) == 0

        # Output result as JSON
        print(json.dumps(result))

        if result.get('success'):
            logger.info(f"✅ Reassignment completed: {result.get('reassigned', 0)}/{result.get('total', 0)} workflows")
            sys.exit(0)
        else:
            logger.error(f"❌ Reassignment failed: {result.get('error', 'Unknown error')}")
            sys.exit(1)

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON input: {e}")
        print(json.dumps({'success': False, 'error': 'Invalid JSON input'}))
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error in role reassignment trigger: {e}", exc_info=True)
        print(json.dumps({'success': False, 'error': str(e)}))
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
