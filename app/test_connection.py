#!/usr/bin/env python3
"""Test database connection after schema consolidation."""
from tsbook import app, db
from models import Tier, Branch, Institution, Role, RoleDuty

app.app_context().push()

print("Testing database connection to scm_terran_society...")
print(f"Tiers: {Tier.query.count()}")
print(f"Branches: {Branch.query.count()}")
print(f"Institutions: {Institution.query.count()}")
print(f"Roles: {Role.query.count()}")
print(f"Duties: {RoleDuty.query.count()}")
print("\n✓ Connection successful! All data accessible.")
