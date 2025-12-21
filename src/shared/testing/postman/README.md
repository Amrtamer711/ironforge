# MMG Postman Collection

API testing collection for MMG CRM with automatic persona-based authentication.

## Quick Start

1. **Import Collection**
   - Open Postman
   - Click Import → Upload Files
   - Select `mmg_api_collection.json`

2. **Import Environment**
   - Click Import → Upload Files
   - Select `mmg_environments.json`

3. **Select Environment**
   - Click the environment dropdown (top right)
   - Select "MMG Environments"

4. **Switch Personas**
   - In the environment, change the `persona` variable
   - Available: `test_admin`, `rep_dubai_1`, `coordinator_1`, `finance_1`, `viewer_only`, etc.

## Features

### Automatic Auth Headers
The collection includes a pre-request script that automatically injects trusted headers based on the selected persona. No need to manually set headers!

### Test Assertions
RBAC testing requests include built-in test assertions:
- Verifies expected status codes (200, 403)
- Checks for detailed error responses
- Validates error codes

### Workflow Scenarios
Complete approval workflow tests that:
1. Set appropriate persona for each step
2. Capture IDs from responses
3. Chain requests together

## Available Personas

| Persona | Profile | Use For |
|---------|---------|---------|
| `test_admin` | System Admin | Full access testing |
| `hos_backlite` | Sales Manager | Manager approvals |
| `rep_dubai_1` | Sales Rep | Create proposals/BOs |
| `rep_dubai_2` | Sales Rep | Sharing tests |
| `coordinator_1` | Coordinator | BO processing |
| `finance_1` | Finance | Final confirmation |
| `viewer_only` | Viewer | Read-only testing |
| `no_permissions` | None | Permission denial |
| `wrong_company` | Sales Rep (Viola) | Cross-company denial |

## Request Folders

### Health & Status
Basic health checks and RBAC context viewing.

### Dev Panel
Impersonation and persona management endpoints.

### Proposals
Full CRUD for proposals.

### Booking Orders
BO listing, approval, and rejection workflows.

### RBAC Testing
Pre-configured tests for permission enforcement:
- Viewer cannot create (403)
- No permissions blocked (403)
- Wrong company denied (403)
- Admin can access all (200)

### Workflow Scenarios
Complete end-to-end approval workflow:
1. Rep creates proposal
2. Rep submits as BO
3. Coordinator approves
4. HoS approves
5. Finance confirms

## Environment Variables

| Variable | Description |
|----------|-------------|
| `base_url` | API base URL (default: `http://localhost:3005`) |
| `persona` | Current test persona ID |
| `proposal_id` | Last created proposal ID |
| `bo_id` | Last created BO ID |
| `workflow_*` | Variables for workflow testing |

## Tips

### Quick Persona Switch
Edit the `persona` variable in the environment to switch users instantly.

### Run Workflow
1. Open the "Workflow Scenarios" folder
2. Click "Run Folder"
3. Watch the complete approval flow execute

### Check Error Details
When a request returns 403, check the response body:
```json
{
  "detail": {
    "error": "Permission denied",
    "code": "PERMISSION_DENIED",
    "required_permission": "sales:proposals:create",
    "user_profile": "viewer",
    "reason": "User with profile 'viewer' does not have 'sales:proposals:create'"
  }
}
```

### Test in Newman (CLI)
```bash
newman run mmg_api_collection.json \
  -e mmg_environments.json \
  --env-var "persona=rep_dubai_1"
```
