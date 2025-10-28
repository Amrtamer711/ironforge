# BackLite Media Sales Proposal Bot

An AI-powered Slack bot for BackLite Media that streamlines sales operations including proposal generation, mockup visualization, and booking order management.

---

## Table of Contents

- [For Sales People & Head of Sales](#for-sales-people--head-of-sales)
  - [1. Proposal Generation](#1-proposal-generation)
  - [2. Mockup Generation](#2-mockup-generation)
  - [3. Booking Order Submission](#3-booking-order-submission)
  - [4. Booking Order Approval (Head of Sales)](#4-booking-order-approval-head-of-sales)
- [For Sales Coordinators](#for-sales-coordinators)
  - [Booking Order Edit Process](#booking-order-edit-process)
- [Technical Setup](#technical-setup)
- [Admin Tools](#admin-tools)

---

## For Sales People & Head of Sales

### 1. Proposal Generation

Generate professional financial proposals for advertising locations with automatic calculations and formatting.

#### Available Location Types

**Digital Locations** (LED screens):
- Net rate + upload fee (automatically added by system)
- No need to specify upload fee - it's pre-configured per location

**Static Locations** (Traditional billboards):
- Net rate + production fee (you must provide)
- Always ask: "What's the production fee?" for static locations

#### How to Generate Proposals

##### Single Location Proposal

```
make me a landmark proposal
start date: Jan 1st 2026
durations: 2 weeks, 4 weeks, 6 weeks
rates: 1.5M, 2.8M, 4M
client: Nike
```

Bot will generate a PowerPoint with multiple duration/rate options.

##### Multiple Locations (Separate Proposals)

```
make me proposals for gateway, jawhara, and landmark
all start Dec 1st
2 weeks each at 2M each
client: Adidas
```

Bot generates:
- Individual PowerPoint for each location
- Combined PDF with all proposals

##### Combined Package Proposal

```
make me a combined package for landmark, gateway, and oryx
landmark: 2 weeks starting Jan 1
gateway: 4 weeks starting Jan 5
oryx: 6 weeks starting Jan 10
total package rate: 5M
client: Coca Cola
```

Bot generates a single slide with all locations and one total rate.

#### Quick Proposal Tips

- **Context switching**: Just mention new location names - bot automatically generates NEW proposals
  - Example: After making "gateway" proposal, just say "jawhara 2M 2 weeks Dec 1" - bot understands it's a new request
- **Intelligent location matching**: Say "gateway" or "the gateway" - bot matches to correct location
- **Abbreviations work**: "uae03", "jawhara", "landmark" all match automatically
- **Missing info**: Bot will ask for any missing details (client name, dates, rates)

#### What You'll Receive

1. **PowerPoint file(s)** - Professional branded proposals
2. **PDF document** - Combined proposals for easy sharing
3. **Database tracking** - All proposals saved automatically

---

### 2. Mockup Generation

Visualize your creative designs on actual billboard locations.

#### Setup Required (One-Time)

Visit the mockup setup website to upload billboard photos:
```
[Bot will provide URL when asked]
```

Upload high-quality photos of billboard locations with frames marked for creative placement.

#### Two Ways to Generate Mockups

##### A) Upload Your Own Creative

Upload image(s) with your request:
```
[Attach image file(s)]
make me a mockup for landmark
```

**Frame Matching**:
- Upload 1 image → Works with any location (image duplicated across frames)
- Upload 3 images → Only uses locations with exactly 3 frames
- Upload N images → Only uses locations with exactly N frames

##### B) AI-Generated Creative

Describe what you want - AI generates it:
```
make me a landmark mockup with a luxury watch on black background with gold accents
```

Bot generates the creative and places it on the billboard automatically.

#### What You'll Receive

- High-quality mockup image
- Creative is automatically sized and placed on billboard
- 30-minute memory: Reuse same creative for different locations

---

### 3. Booking Order Submission

Submit booking orders for approval workflow (Sales → Coordinator → Head of Sales → Finance).

#### How to Submit a Booking Order

Upload the booking order document with your message:
```
[Attach PDF/Excel/Image file]
parse this booking order for Backlite
```

Or:
```
[Attach file]
booking order for Viola, upload fee is 2000, client is Nike
```

#### What Happens Next

1. **AI Parsing**: Bot extracts all data (client, locations, fees, dates, rates)
2. **Review**: You review extracted data in thread
3. **Confirmation**: Bot shows preview with calculated totals (VAT, gross)
4. **Approval Flow Begins**:
   - ✅ **Sales Person** (you) - Approve to send forward
   - ⏳ **Sales Coordinator** - Reviews and approves
   - ⏳ **Head of Sales** - Final approval
   - ✅ **Finance** - Receives approved booking order

#### During Approval

- You can **edit** booking order data in the thread (change fees, locations, dates)
- You can **reject** and provide feedback
- Bot recalculates VAT/totals automatically when you edit fees
- Each approver sees current status and can approve/reject

#### Key Information Extracted

- Client name and brand/campaign
- Category (OOH, DOOH, Print, etc.)
- All locations with individual net amounts
- Municipality fee, production/upload fee
- Payment terms and tenure
- Automatic VAT calculation (5%)
- Automatic gross total calculation

---

### 4. Booking Order Approval (Head of Sales)

As Head of Sales, you're part of the approval workflow.

#### When You Receive a Booking Order

You'll get a Slack message with:
- All booking order details
- Current approval status
- PDF preview of the booking order
- **Accept** and **Reject** buttons

#### How to Approve

1. **Review** the booking order details
2. Click **Accept** button
3. Bot automatically:
   - Adds your signature to the booking order (using your configured name)
   - Sends to Finance team
   - Notifies all stakeholders
   - Updates workflow status

#### How to Reject

1. Click **Reject** button
2. Write reason in the thread
3. Bot sends feedback back to Sales Coordinator with your comments

#### After Approval

- Finance team receives the approved booking order
- Booking order PDF includes your signature
- All stakeholders are notified
- Status tracked in database

---

## For Sales Coordinators

### Booking Order Edit Process

As a Sales Coordinator, you're the second approval stage in the workflow.

#### Your Role in the Workflow

```
Sales Person → YOU (Sales Coordinator) → Head of Sales → Finance
```

#### When You Receive a Booking Order

You'll get a Slack DM with:
- Complete booking order details
- All extracted data (client, locations, fees, dates)
- PDF preview
- **Accept** and **Reject** buttons

#### Review Process

Check for:
- ✅ Client name and campaign details correct
- ✅ Locations are correct with proper net amounts
- ✅ Municipality fee included (if applicable)
- ✅ Production/upload fees correct
- ✅ Payment terms accurate
- ✅ Tenure dates correct
- ✅ VAT calculation (5%) looks correct
- ✅ Gross total is accurate

#### How to Request Edits

If something needs to be changed:

1. **Reply in the thread** with what needs changing:
   ```
   change municipality fee to 5000
   ```

   Or:
   ```
   update location dubai_gateway net amount to 150000
   ```

2. **Bot updates automatically**:
   - Recalculates VAT and gross total
   - Updates the PDF preview
   - Shows you the new values

3. **Multiple edits supported**:
   ```
   change client to "Nike Middle East"
   change payment terms to "50% upfront, 50% on installation"
   change tenure to "1st December 2025 - 31st December 2025"
   ```

#### Edit Examples

##### Change fees:
```
change municipality fee to 8000
change production upload fee to 3000
```

##### Change location amounts:
```
change location landmark net amount to 250000
```

##### Change client details:
```
change client to "Adidas UAE"
change brand campaign to "Winter Collection 2025"
```

##### Change dates:
```
change tenure to "1st Jan 2026 - 31st Jan 2026"
```

##### Change payment terms:
```
change payment terms to "100% advance payment"
```

#### What Gets Recalculated Automatically

When you edit:
- **Fees** (municipality, production/upload) → Net pre-VAT recalculated
- **Location amounts** → Net pre-VAT recalculated
- **Net pre-VAT changes** → VAT (5%) recalculated
- **VAT changes** → Gross total recalculated

Bot ensures all totals are always accurate.

#### How to Approve

Once everything looks correct:

1. Click **Accept** button
2. Bot automatically:
   - Sends to Head of Sales
   - Updates all stakeholders
   - Updates workflow status
   - Notifies you of successful submission

#### How to Reject

If booking order needs major changes:

1. Click **Reject** button
2. Write detailed feedback in thread:
   ```
   Rejecting because:
   - Client name needs confirmation from sales
   - Location rates don't match approved rate card
   - Payment terms need finance approval first
   ```
3. Bot sends your feedback back to Sales Person
4. Sales Person can resubmit after addressing issues

#### Key Things to Know

- **Edit in thread**: Don't approve until everything is correct - just edit in the thread
- **Recalculation**: Bot handles all math automatically
- **Preview updates**: PDF preview updates after each edit
- **No rush**: Take your time to review - workflow waits for your approval
- **Context aware**: Bot understands what you want to edit based on your message
- **Multiple fields**: You can change multiple things at once

#### Common Edit Scenarios

##### Scenario 1: Wrong Fee Amount
```
Coordinator: "change municipality fee to 12000"
Bot: Updates fee, recalculates net, VAT, gross, shows new totals
Coordinator: Reviews, clicks Accept
```

##### Scenario 2: Location Amount Error
```
Coordinator: "change location dubai_gateway net amount to 180000"
Bot: Updates location, recalculates totals
Coordinator: "looks good now" → Clicks Accept
```

##### Scenario 3: Multiple Changes Needed
```
Coordinator: "change client to Nike UAE"
Coordinator: "change payment terms to 50% advance 50% on completion"
Coordinator: "change municipality fee to 8000"
Bot: Updates all three, recalculates
Coordinator: Reviews all changes, clicks Accept
```

##### Scenario 4: Major Issues - Rejection
```
Coordinator: Reviews booking order, spots issues
Coordinator: Clicks Reject
Coordinator: "Location rates don't match rate card. Dubai Gateway should be 200K not 150K. Please resubmit with correct rates."
Bot: Sends feedback to Sales Person
```

---

## Technical Setup

### Environment Variables

Required:
```
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
OPENAI_API_KEY=sk-...
DATABASE_URL=sqlite:///./proposals.db
```

### Database

SQLite database with tables:
- `proposals` - All generated proposals
- `booking_orders` - All booking orders with workflow status
- `workflow_state` - Active approval workflows
- `mockup_frames` - Billboard photo frame coordinates

### Deployment

The bot runs on Render and connects to Slack workspace. Updates are deployed via GitHub:
- `dev` branch - Testing environment
- `main` branch - Production environment

---

## Admin Tools

Admin users have access to additional tools:

### Location Management
```
add location [provides form for location details]
delete location [location_name]
list locations
```

### Database Exports
```
export all proposals to excel
export all booking orders to excel
```

### Configuration
- **hos_config.json** - Configure Head of Sales and Finance team members
- **Admin permissions** - Set via slack_user_id in hos_config.json

### Booking Order Number Format
- **User-facing**: DPD-XXX, VLA-XXX (shown on documents)
- **Internal**: bo_TIMESTAMP_COMPANY (database reference)

---

## Support

For issues or questions:
1. Check the bot's help: Send "help" in Slack
2. Check logs for errors (admin access required)
3. Contact development team

---

## Key Features

✅ **Intelligent context switching** - Bot recognizes new requests immediately
✅ **Location name inference** - Say "gateway" or "the gateway" - bot matches correctly
✅ **Automatic calculations** - VAT, totals, fees calculated automatically
✅ **Edit-friendly** - Change any field, bot recalculates everything
✅ **Multi-stage approval** - Sales → Coordinator → HoS → Finance
✅ **Digital signatures** - Automatically adds Head of Sales signature
✅ **Database tracking** - All proposals and booking orders saved
✅ **PDF generation** - Professional documents for all outputs
✅ **Mockup visualization** - Upload-based or AI-generated creatives
✅ **Multi-company support** - Backlite and Viola with separate configurations

---

**Version**: 1.0
**Last Updated**: October 2025
