# Frontend Requirements for Amr

## Pending

### Questions / Confirmations
1. **Companies Endpoint** - Confirm if `/dev/companies` path is correct for company details

### Admin Features
2. **User - multiple Profile sets** - Assign/list multiple profiles per user
3. **User - multiple Permission sets** - Assign multiple permission sets per user
4. **Profile to Permission-Set relation** - Link profiles to permission sets
5. **Hide unused tabs** - Hide teams, sharing rules etc. that are not in use
6. **Add Location UI** - List out the locations for admins

### Mockups
7. **Template thumbnails** - Save `xxxx_n_thumb.png` alongside templates for faster loading. Include in response as `thumbnail` field
8. **Mockup history** - Show history with date + generated image
9. **Mockup frame edit endpoint** - Endpoint to get frame details/config for editing existing templates
   - **Answer**: Yes, use `GET /api/mockup-frames/{company}/{location_key}/frame?time_of_day=day&finish=gold` to get frame data

---

## Completed

### Separate Proposals - Multiple Dates + Payment Terms
**Issue**: Separate proposals were not showing different `start_dates` and `payment_terms` was defaulting to "100% upfront"

**Fix**: Now supports `start_dates` array parallel with `durations` and `net_rates`. Each option gets its own column in the financial slide.

**Example Request**:
```json
{
    "proposals": [{
        "location": "oryx",
        "start_dates": ["01/01/2026", "01/02/2026", "01/03/2026"],
        "durations": ["2 Weeks", "2 Weeks", "3 Weeks"],
        "net_rates": ["AED 12,000", "AED 13,000", "AED 32,000"]
    }],
    "client_name": "Etisalat",
    "proposal_type": "separate",
    "payment_terms": "70% upfront, 30% after"
}
```

**Status**: Fixed in commit `5ed9e78`
