"""Account admin screens remain deferred; no models are registered yet.

The custom user needs forms/fieldsets adapted to email before adding a UserAdmin.
Business administrator roles do not automatically grant Django staff/superuser
access. Role-management operations must use the appropriate authorization checks.
"""
