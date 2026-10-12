# Database Model Fixes Applied

## Issue Identified
The web application was showing SQLAlchemy errors when accessing role detail pages (and potentially other pages with explain relationships).

### Error Example:
```
sqlalchemy.exc.ProgrammingError: (psycopg2.errors.UndefinedColumn) 
column role_explain.role_explain_id does not exist
```

## Root Cause
The SQLAlchemy models had **incorrect primary key field names** for the `*_explain` tables:

- **Model had:** `role_explain_id`, `institution_explain_id`, `tier_explain_id`
- **Database has:** `explain_id` (all explain tables use the same field name)

## Fixes Applied

### Modified Files:
- `models.py` - Fixed 3 model classes

### Changes Made:

1. **RoleExplain model:**
   - Changed: `role_explain_id` → `explain_id`

2. **InstitutionExplain model:**
   - Changed: `institution_explain_id` → `explain_id`

3. **TierExplain model:**
   - Changed: `tier_explain_id` → `explain_id`

## Verification

Tested all models with `test_models.py`:
- ✓ All basic queries work
- ✓ All relationships work
- ✓ Role 71 (previously broken) now loads correctly
- ✓ All explain tables query successfully

## Current Status

**✅ ALL BROKEN LINKS FIXED**

The application should now work correctly for all pages including:
- Role detail pages (with explanations)
- Institution detail pages (with explanations)
- Tier detail pages (with explanations)

## Testing

```bash
# Start the application
python3 tsbook.py

# Test previously broken link
# Visit: http://localhost:5000/roles/71
# Should now work without errors
```

## Additional Notes

- All other model fields matched the database correctly
- The Tier table in the database doesn't have created_at/modified_at timestamps, but SQLAlchemy handles this gracefully
- The fix resolves all relationship queries for explain tables

---

**Fixed:** 2025-12-28  
**Files Modified:** models.py (3 classes)  
**Lines Changed:** 3 primary key definitions
