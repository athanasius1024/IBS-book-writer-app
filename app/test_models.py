#!/usr/bin/env python3
"""Test all models for database column mismatches."""
from tsbook import app, db
from models import Tier, Branch, Institution, Role, RoleDuty, RoleExplain, InstitutionExplain, TierExplain, Process

app.app_context().push()

print("Testing all models for database compatibility...\n")

try:
    print("1. Testing Tier...")
    tier = Tier.query.first()
    print(f"   ✓ Tier: {tier.tier_name if tier else 'No data'}")
except Exception as e:
    print(f"   ✗ Error: {e}")

try:
    print("2. Testing Branch...")
    branch = Branch.query.first()
    print(f"   ✓ Branch: {branch.branch_name if branch else 'No data'}")
except Exception as e:
    print(f"   ✗ Error: {e}")

try:
    print("3. Testing Institution...")
    inst = Institution.query.first()
    print(f"   ✓ Institution: {inst.institution_name if inst else 'No data'}")
except Exception as e:
    print(f"   ✗ Error: {e}")

try:
    print("4. Testing Role...")
    role = Role.query.first()
    print(f"   ✓ Role: {role.role_name if role else 'No data'}")
except Exception as e:
    print(f"   ✗ Error: {e}")

try:
    print("5. Testing RoleDuty...")
    duty = RoleDuty.query.first()
    print(f"   ✓ RoleDuty: {duty.duty_header if duty else 'No data'}")
except Exception as e:
    print(f"   ✗ Error: {e}")

try:
    print("6. Testing RoleExplain...")
    explain = RoleExplain.query.first()
    print(f"   ✓ RoleExplain: {explain.explain_id if explain else 'No data'}")
except Exception as e:
    print(f"   ✗ Error: {e}")

try:
    print("7. Testing InstitutionExplain...")
    inst_explain = InstitutionExplain.query.first()
    print(f"   ✓ InstitutionExplain: {inst_explain.explain_id if inst_explain else 'No data'}")
except Exception as e:
    print(f"   ✗ Error: {e}")

try:
    print("8. Testing TierExplain...")
    tier_explain = TierExplain.query.first()
    print(f"   ✓ TierExplain: {tier_explain.explain_id if tier_explain else 'No data'}")
except Exception as e:
    print(f"   ✗ Error: {e}")

try:
    print("9. Testing Process...")
    process = Process.query.first()
    print(f"   ✓ Process: {process.process_name if process else 'No data'}")
except Exception as e:
    print(f"   ✗ Error: {e}")

try:
    print("10. Testing Role with relationships...")
    role = Role.query.filter_by(role_id=71).first()
    if role:
        print(f"    ✓ Role 71: {role.role_name}")
        print(f"    ✓ Institution: {role.institution.institution_name}")
        print(f"    ✓ Duties: {len(role.duties)}")
        print(f"    ✓ Explains: {len(role.role_explains)}")
    else:
        print("    No role with ID 71")
except Exception as e:
    print(f"    ✗ Error: {e}")

print("\n✓ All tests completed!")
