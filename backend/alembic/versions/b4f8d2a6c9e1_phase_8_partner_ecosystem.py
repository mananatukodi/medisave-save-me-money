"""Phase 8: partner ecosystem

Revision ID: b4f8d2a6c9e1
Revises: c7d2e9a41b83
Create Date: 2026-09-21

Additive only: sixteen new partner tables + idempotent feature-flag seed rows.
No Phase 1-7 tables are altered or removed; existing provider data is linked
(not duplicated) through partner_profiles FK columns.
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = 'b4f8d2a6c9e1'
down_revision = 'c7d2e9a41b83'
branch_labels = None
depends_on = None

PARTNER_FLAGS = (
    ("partner_ecosystem", "Partner ecosystem core (organizations + members)", False),
    ("partner_onboarding", "Partner registration/onboarding workflow", False),
    ("partner_verification", "Partner verification/admin review workflow", False),
    ("partner_services", "Partner service catalog management", False),
    ("partner_claims", "Partner claims architecture", False),
    ("partner_settlement", "Partner settlement records (finance-recorded)", False),
    ("partner_webhooks", "Partner webhook event ledger + endpoints", False),
    ("partner_api", "Partner API key credentials", False),
    ("partner_lab", "Diagnostics lab partner module", False),
    ("partner_insurance", "Insurance partner module", False),
    ("partner_emergency", "Emergency provider (ambulance) partner module", False),
)


def upgrade() -> None:
    # ---- organizations ----
    op.create_table(
        'organizations',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_type', sa.String(length=30), nullable=False),
        sa.Column('legal_name', sa.String(length=255), nullable=False),
        sa.Column('display_name', sa.String(length=255), nullable=False),
        sa.Column('registration_number', sa.String(length=80), nullable=False, server_default=''),
        sa.Column('tax_identifier', sa.String(length=80), nullable=True),
        sa.Column('phone', sa.String(length=20), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('address_line', sa.String(length=300), nullable=False, server_default=''),
        sa.Column('city', sa.String(length=120), nullable=True),
        sa.Column('state', sa.String(length=120), nullable=True),
        sa.Column('pincode', sa.String(length=12), nullable=True),
        sa.Column('latitude', sa.String(length=24), nullable=True),
        sa.Column('longitude', sa.String(length=24), nullable=True),
        sa.Column('status', sa.String(length=24), nullable=False, server_default='DRAFT'),
        sa.Column('verification_status', sa.String(length=24), nullable=False, server_default='UNVERIFIED'),
        sa.Column('created_by_user_id', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name='fk_org_creator'),
        sa.PrimaryKeyConstraint('id', name='pk_organizations'),
    )
    op.create_index('ix_organizations_organization_type', 'organizations', ['organization_type'])
    op.create_index('ix_organizations_status', 'organizations', ['status'])
    op.create_index('ix_organizations_city', 'organizations', ['city'])
    op.create_index('ix_organizations_pincode', 'organizations', ['pincode'])
    op.create_index('ix_organizations_created_by_user_id', 'organizations', ['created_by_user_id'])
    op.create_index('ix_organizations_type_status', 'organizations', ['organization_type', 'status'])
    op.create_index(
        'uq_organization_registration',
        'organizations',
        ['organization_type', 'registration_number'],
        unique=True,
        postgresql_where=sa.text("registration_number <> ''"),
        sqlite_where=sa.text("registration_number <> ''"),
    )

    # ---- organization_members ----
    op.create_table(
        'organization_members',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('partner_role', sa.String(length=30), nullable=False, server_default='PARTNER_STAFF'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('granted_by_user_id', sa.String(length=36), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name='fk_org_member_org'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_org_member_user'),
        sa.ForeignKeyConstraint(['granted_by_user_id'], ['users.id'], name='fk_org_member_granter'),
        sa.PrimaryKeyConstraint('id', name='pk_organization_members'),
    )
    op.create_index('ix_organization_members_organization_id', 'organization_members', ['organization_id'])
    op.create_index('ix_organization_members_user_id', 'organization_members', ['user_id'])
    op.create_index('ix_org_members_user', 'organization_members', ['user_id', 'is_active'])
    op.create_index(
        'uq_org_member_active',
        'organization_members',
        ['organization_id', 'user_id'],
        unique=True,
        postgresql_where=sa.text('is_active = true'),
        sqlite_where=sa.text('is_active = 1'),
    )

    # ---- partner_profiles ----
    op.create_table(
        'partner_profiles',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('metadata_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('doctor_id', sa.String(length=36), nullable=True),
        sa.Column('hospital_id', sa.String(length=36), nullable=True),
        sa.Column('pharmacy_id', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name='fk_partner_profile_org'),
        sa.ForeignKeyConstraint(['doctor_id'], ['doctors.id'], name='fk_partner_profile_doctor'),
        sa.ForeignKeyConstraint(['hospital_id'], ['hospitals.id'], name='fk_partner_profile_hospital'),
        sa.ForeignKeyConstraint(['pharmacy_id'], ['pharmacies.id'], name='fk_partner_profile_pharmacy'),
        sa.PrimaryKeyConstraint('id', name='pk_partner_profiles'),
        sa.UniqueConstraint('organization_id', name='uq_partner_profile_org'),
    )
    op.create_index('ix_partner_profiles_organization_id', 'partner_profiles', ['organization_id'])
    op.create_index('ix_partner_profiles_doctor_id', 'partner_profiles', ['doctor_id'])
    op.create_index('ix_partner_profiles_hospital_id', 'partner_profiles', ['hospital_id'])
    op.create_index('ix_partner_profiles_pharmacy_id', 'partner_profiles', ['pharmacy_id'])

    # ---- partner_lifecycle_events ----
    op.create_table(
        'partner_lifecycle_events',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('previous_status', sa.String(length=24), nullable=False, server_default=''),
        sa.Column('new_status', sa.String(length=24), nullable=False),
        sa.Column('actor_user_id', sa.String(length=36), nullable=True),
        sa.Column('note', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name='fk_partner_lifecycle_org'),
        sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], name='fk_partner_lifecycle_actor'),
        sa.PrimaryKeyConstraint('id', name='pk_partner_lifecycle_events'),
    )
    op.create_index('ix_partner_lifecycle_events_organization_id', 'partner_lifecycle_events', ['organization_id'])
    op.create_index('ix_partner_lifecycle_events_created_at', 'partner_lifecycle_events', ['created_at'])

    # ---- partner_documents ----
    op.create_table(
        'partner_documents',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('document_type', sa.String(length=40), nullable=False),
        sa.Column('file_id', sa.String(length=36), nullable=True),
        sa.Column('storage_reference', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('checksum', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('issued_at', sa.Date(), nullable=True),
        sa.Column('expires_at', sa.Date(), nullable=True),
        sa.Column('verification_status', sa.String(length=20), nullable=False, server_default='UPLOADED'),
        sa.Column('verified_by_user_id', sa.String(length=36), nullable=True),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('review_note', sa.Text(), nullable=False, server_default=''),
        sa.Column('uploaded_by_user_id', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name='fk_partner_document_org'),
        sa.ForeignKeyConstraint(['file_id'], ['stored_files.id'], name='fk_partner_document_file'),
        sa.ForeignKeyConstraint(['verified_by_user_id'], ['users.id'], name='fk_partner_document_verifier'),
        sa.ForeignKeyConstraint(['uploaded_by_user_id'], ['users.id'], name='fk_partner_document_uploader'),
        sa.PrimaryKeyConstraint('id', name='pk_partner_documents'),
    )
    op.create_index('ix_partner_documents_organization_id', 'partner_documents', ['organization_id'])
    op.create_index('ix_partner_documents_verification_status', 'partner_documents', ['verification_status'])
    op.create_index('ix_partner_documents_org_status', 'partner_documents', ['organization_id', 'verification_status'])

    # ---- partner_services ----
    op.create_table(
        'partner_services',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('service_type', sa.String(length=40), nullable=False),
        sa.Column('name', sa.String(length=160), nullable=False),
        sa.Column('description', sa.Text(), nullable=False, server_default=''),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='ACTIVE'),
        sa.Column('price', sa.Float(), nullable=True),
        sa.Column('currency', sa.String(length=8), nullable=False, server_default='INR'),
        sa.Column('price_verification_status', sa.String(length=20), nullable=False, server_default='UNVERIFIED'),
        sa.Column('price_source', sa.String(length=120), nullable=False, server_default='partner_declared'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name='fk_partner_service_org'),
        sa.PrimaryKeyConstraint('id', name='pk_partner_services'),
    )
    op.create_index('ix_partner_services_organization_id', 'partner_services', ['organization_id'])
    op.create_index('ix_partner_services_service_type', 'partner_services', ['service_type'])
    op.create_index('ix_partner_services_org_type', 'partner_services', ['organization_id', 'service_type'])

    # ---- partner_claims ----
    op.create_table(
        'partner_claims',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('patient_user_id', sa.String(length=36), nullable=False),
        sa.Column('claim_number', sa.String(length=60), nullable=False, server_default=''),
        sa.Column('subject_type', sa.String(length=24), nullable=False, server_default='OTHER'),
        sa.Column('subject_id', sa.String(length=36), nullable=True),
        sa.Column('status', sa.String(length=40), nullable=False, server_default='DRAFT'),
        sa.Column('description', sa.Text(), nullable=False, server_default=''),
        sa.Column('amount', sa.Float(), nullable=True),
        sa.Column('approved_amount', sa.Float(), nullable=True),
        sa.Column('currency', sa.String(length=8), nullable=False, server_default='INR'),
        sa.Column('submitted_by_user_id', sa.String(length=36), nullable=True),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('decided_by_user_id', sa.String(length=36), nullable=True),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name='fk_partner_claim_org'),
        sa.ForeignKeyConstraint(['patient_user_id'], ['users.id'], name='fk_partner_claim_patient'),
        sa.ForeignKeyConstraint(['submitted_by_user_id'], ['users.id'], name='fk_partner_claim_submitter'),
        sa.ForeignKeyConstraint(['decided_by_user_id'], ['users.id'], name='fk_partner_claim_decider'),
        sa.PrimaryKeyConstraint('id', name='pk_partner_claims'),
    )
    op.create_index('ix_partner_claims_organization_id', 'partner_claims', ['organization_id'])
    op.create_index('ix_partner_claims_patient_user_id', 'partner_claims', ['patient_user_id'])
    op.create_index('ix_partner_claims_status', 'partner_claims', ['status'])
    op.create_index('ix_partner_claims_subject_id', 'partner_claims', ['subject_id'])
    op.create_index('ix_partner_claims_org_status', 'partner_claims', ['organization_id', 'status'])
    op.create_index(
        'uq_partner_claim_number',
        'partner_claims',
        ['organization_id', 'claim_number'],
        unique=True,
        postgresql_where=sa.text("claim_number <> ''"),
        sqlite_where=sa.text("claim_number <> ''"),
    )

    # ---- partner_claim_events ----
    op.create_table(
        'partner_claim_events',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('claim_id', sa.String(length=36), nullable=False),
        sa.Column('previous_status', sa.String(length=40), nullable=False, server_default=''),
        sa.Column('new_status', sa.String(length=40), nullable=False),
        sa.Column('actor_user_id', sa.String(length=36), nullable=True),
        sa.Column('note', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['claim_id'], ['partner_claims.id'], name='fk_partner_claim_event_claim'),
        sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], name='fk_partner_claim_event_actor'),
        sa.PrimaryKeyConstraint('id', name='pk_partner_claim_events'),
    )
    op.create_index('ix_partner_claim_events_claim_id', 'partner_claim_events', ['claim_id'])
    op.create_index('ix_partner_claim_events_created_at', 'partner_claim_events', ['created_at'])
    op.create_index('ix_partner_claim_events_claim', 'partner_claim_events', ['claim_id'])

    # ---- partner_lab_tests ----
    op.create_table(
        'partner_lab_tests',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('code', sa.String(length=60), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=False, server_default=''),
        sa.Column('category', sa.String(length=80), nullable=False, server_default=''),
        sa.Column('sample_type', sa.String(length=80), nullable=False, server_default=''),
        sa.Column('preparation_notes', sa.Text(), nullable=False, server_default=''),
        sa.Column('price', sa.Float(), nullable=True),
        sa.Column('currency', sa.String(length=8), nullable=False, server_default='INR'),
        sa.Column('verification_status', sa.String(length=20), nullable=False, server_default='UNVERIFIED'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name='fk_partner_lab_test_org'),
        sa.PrimaryKeyConstraint('id', name='pk_partner_lab_tests'),
    )
    op.create_index('ix_partner_lab_tests_organization_id', 'partner_lab_tests', ['organization_id'])
    op.create_index('ix_partner_lab_tests_verification_status', 'partner_lab_tests', ['verification_status'])
    op.create_index(
        'uq_partner_lab_test_code',
        'partner_lab_tests',
        ['organization_id', 'code'],
        unique=True,
        postgresql_where=sa.text('is_active = true'),
        sqlite_where=sa.text('is_active = 1'),
    )

    # ---- partner_lab_bookings ----
    op.create_table(
        'partner_lab_bookings',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('test_id', sa.String(length=36), nullable=False),
        sa.Column('patient_user_id', sa.String(length=36), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='REQUESTED'),
        sa.Column('collection_mode', sa.String(length=20), nullable=False, server_default='CENTER_VISIT'),
        sa.Column('scheduled_for', sa.DateTime(timezone=True), nullable=True),
        sa.Column('report_reference', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('health_record_id', sa.String(length=36), nullable=True),
        sa.Column('notes', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name='fk_partner_lab_booking_org'),
        sa.ForeignKeyConstraint(['test_id'], ['partner_lab_tests.id'], name='fk_partner_lab_booking_test'),
        sa.ForeignKeyConstraint(['patient_user_id'], ['users.id'], name='fk_partner_lab_booking_patient'),
        sa.ForeignKeyConstraint(['health_record_id'], ['health_records.id'], name='fk_partner_lab_booking_record'),
        sa.PrimaryKeyConstraint('id', name='pk_partner_lab_bookings'),
    )
    op.create_index('ix_partner_lab_bookings_organization_id', 'partner_lab_bookings', ['organization_id'])
    op.create_index('ix_partner_lab_bookings_test_id', 'partner_lab_bookings', ['test_id'])
    op.create_index('ix_partner_lab_bookings_patient_user_id', 'partner_lab_bookings', ['patient_user_id'])
    op.create_index('ix_partner_lab_bookings_status', 'partner_lab_bookings', ['status'])
    op.create_index('ix_partner_lab_bookings_org_status', 'partner_lab_bookings', ['organization_id', 'status'])

    # ---- partner_insurance_products ----
    op.create_table(
        'partner_insurance_products',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('product_name', sa.String(length=200), nullable=False),
        sa.Column('product_type', sa.String(length=60), nullable=False, server_default=''),
        sa.Column('description', sa.Text(), nullable=False, server_default=''),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='ACTIVE'),
        sa.Column('claim_intake_supported', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name='fk_partner_ins_product_org'),
        sa.PrimaryKeyConstraint('id', name='pk_partner_insurance_products'),
    )
    op.create_index('ix_partner_insurance_products_organization_id', 'partner_insurance_products', ['organization_id'])

    # ---- partner_insurance_policies ----
    op.create_table(
        'partner_insurance_policies',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('product_id', sa.String(length=36), nullable=True),
        sa.Column('patient_user_id', sa.String(length=36), nullable=False),
        sa.Column('policy_number', sa.String(length=80), nullable=False, server_default=''),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='PROPOSED'),
        sa.Column('metadata_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name='fk_partner_ins_policy_org'),
        sa.ForeignKeyConstraint(['product_id'], ['partner_insurance_products.id'], name='fk_partner_ins_policy_product'),
        sa.ForeignKeyConstraint(['patient_user_id'], ['users.id'], name='fk_partner_ins_policy_patient'),
        sa.PrimaryKeyConstraint('id', name='pk_partner_insurance_policies'),
    )
    op.create_index('ix_partner_insurance_policies_organization_id', 'partner_insurance_policies', ['organization_id'])
    op.create_index('ix_partner_insurance_policies_patient_user_id', 'partner_insurance_policies', ['patient_user_id'])

    # ---- partner_insurance_claim_details ----
    op.create_table(
        'partner_insurance_claim_details',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('claim_id', sa.String(length=36), nullable=False),
        sa.Column('policy_id', sa.String(length=36), nullable=True),
        sa.Column('documents_ref', sa.Text(), nullable=False, server_default=''),
        sa.Column('insurer_note', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['claim_id'], ['partner_claims.id'], name='fk_partner_ins_claim_claim'),
        sa.ForeignKeyConstraint(['policy_id'], ['partner_insurance_policies.id'], name='fk_partner_ins_claim_policy'),
        sa.PrimaryKeyConstraint('id', name='pk_partner_insurance_claim_details'),
        sa.UniqueConstraint('claim_id', name='uq_partner_ins_claim_detail_claim'),
    )
    op.create_index('ix_partner_insurance_claim_details_claim_id', 'partner_insurance_claim_details', ['claim_id'])

    # ---- partner_integrations ----
    op.create_table(
        'partner_integrations',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('integration_kind', sa.String(length=24), nullable=False, server_default='API_KEY'),
        sa.Column('name', sa.String(length=120), nullable=False, server_default=''),
        sa.Column('endpoint_url', sa.String(length=500), nullable=True),
        sa.Column('key_prefix', sa.String(length=16), nullable=False, server_default=''),
        sa.Column('key_hash', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('scopes', sa.String(length=300), nullable=False, server_default='read'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='ACTIVE'),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by_user_id', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name='fk_partner_integration_org'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name='fk_partner_integration_creator'),
        sa.PrimaryKeyConstraint('id', name='pk_partner_integrations'),
    )
    op.create_index('ix_partner_integrations_organization_id', 'partner_integrations', ['organization_id'])
    op.create_index('ix_partner_integrations_key_prefix', 'partner_integrations', ['key_prefix'])
    op.create_index('ix_partner_integrations_org_kind', 'partner_integrations', ['organization_id', 'integration_kind'])

    # ---- partner_webhook_events ----
    op.create_table(
        'partner_webhook_events',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('event_id', sa.String(length=64), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('event_type', sa.String(length=40), nullable=False),
        sa.Column('payload', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('delivery_status', sa.String(length=20), nullable=False, server_default='PENDING'),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_response_code', sa.Integer(), nullable=True),
        sa.Column('detail', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name='fk_partner_webhook_event_org'),
        sa.PrimaryKeyConstraint('id', name='pk_partner_webhook_events'),
    )
    op.create_index('ix_partner_webhook_events_organization_id', 'partner_webhook_events', ['organization_id'])
    op.create_index('ix_partner_webhook_events_delivery_status', 'partner_webhook_events', ['delivery_status'])
    op.create_index('ix_partner_webhook_events_created_at', 'partner_webhook_events', ['created_at'])
    op.create_index('uq_partner_webhook_event_id', 'partner_webhook_events', ['event_id'], unique=True)

    # ---- partner_settlements ----
    op.create_table(
        'partner_settlements',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('period_start', sa.Date(), nullable=True),
        sa.Column('period_end', sa.Date(), nullable=True),
        sa.Column('gross_amount', sa.Float(), nullable=True),
        sa.Column('platform_fee', sa.Float(), nullable=True),
        sa.Column('net_amount', sa.Float(), nullable=True),
        sa.Column('currency', sa.String(length=8), nullable=False, server_default='INR'),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='RECORDED'),
        sa.Column('external_reference', sa.String(length=120), nullable=False, server_default=''),
        sa.Column('note', sa.Text(), nullable=False, server_default=''),
        sa.Column('recorded_by_user_id', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name='fk_partner_settlement_org'),
        sa.ForeignKeyConstraint(['recorded_by_user_id'], ['users.id'], name='fk_partner_settlement_recorder'),
        sa.PrimaryKeyConstraint('id', name='pk_partner_settlements'),
    )
    op.create_index('ix_partner_settlements_organization_id', 'partner_settlements', ['organization_id'])
    op.create_index(
        'uq_partner_settlement_period',
        'partner_settlements',
        ['organization_id', 'period_start', 'period_end'],
        unique=True,
        postgresql_where=sa.text('period_start IS NOT NULL AND period_end IS NOT NULL'),
        sqlite_where=sa.text('period_start IS NOT NULL AND period_end IS NOT NULL'),
    )

    # ---- partner_commissions ----
    op.create_table(
        'partner_commissions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('commission_type', sa.String(length=20), nullable=False, server_default='PERCENT'),
        sa.Column('commission_value', sa.Float(), nullable=False, server_default='0'),
        sa.Column('currency', sa.String(length=8), nullable=False, server_default='INR'),
        sa.Column('service_type', sa.String(length=40), nullable=True),
        sa.Column('effective_from', sa.Date(), nullable=True),
        sa.Column('effective_until', sa.Date(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='ACTIVE'),
        sa.Column('created_by_user_id', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name='fk_partner_commission_org'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name='fk_partner_commission_creator'),
        sa.PrimaryKeyConstraint('id', name='pk_partner_commissions'),
    )
    op.create_index('ix_partner_commissions_organization_id', 'partner_commissions', ['organization_id'])

    # ---- partner_notifications ----
    op.create_table(
        'partner_notifications',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('recipient_user_id', sa.String(length=36), nullable=True),
        sa.Column('channel', sa.String(length=10), nullable=False, server_default='IN_APP'),
        sa.Column('status', sa.String(length=10), nullable=False, server_default='QUEUED'),
        sa.Column('event_type', sa.String(length=40), nullable=False, server_default=''),
        sa.Column('title', sa.String(length=200), nullable=False, server_default=''),
        sa.Column('body', sa.Text(), nullable=False, server_default=''),
        sa.Column('resource_type', sa.String(length=40), nullable=False, server_default=''),
        sa.Column('resource_id', sa.String(length=36), nullable=True),
        sa.Column('provider_name', sa.String(length=60), nullable=True),
        sa.Column('error_detail', sa.String(length=200), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name='fk_partner_notification_org'),
        sa.ForeignKeyConstraint(['recipient_user_id'], ['users.id'], name='fk_partner_notification_recipient'),
        sa.PrimaryKeyConstraint('id', name='pk_partner_notifications'),
    )
    op.create_index('ix_partner_notifications_organization_id', 'partner_notifications', ['organization_id'])
    op.create_index('ix_partner_notifications_recipient_user_id', 'partner_notifications', ['recipient_user_id'])
    op.create_index('ix_partner_notifications_status', 'partner_notifications', ['status'])
    op.create_index('ix_partner_notifications_created_at', 'partner_notifications', ['created_at'])

    # ---- feature flags (idempotent seed) ----
    import datetime as _dt

    from sqlalchemy import Boolean as SaBoolean
    from sqlalchemy import column, table, String as SaString

    flags_table = table(
        'feature_flags',
        column('key', SaString),
        column('description', SaString),
        column('is_enabled', SaBoolean),
        column('updated_at', sa.DateTime),
    )
    now = _dt.datetime.now(_dt.UTC)
    for key, description, enabled in PARTNER_FLAGS:
        op.bulk_insert(
            flags_table,
            [{'key': key, 'description': description, 'is_enabled': enabled, 'updated_at': now}],
        )


def downgrade() -> None:
    op.drop_table('partner_notifications')
    op.drop_table('partner_commissions')
    op.drop_table('partner_settlements')
    op.drop_table('partner_webhook_events')
    op.drop_table('partner_integrations')
    op.drop_table('partner_insurance_claim_details')
    op.drop_table('partner_insurance_policies')
    op.drop_table('partner_insurance_products')
    op.drop_table('partner_lab_bookings')
    op.drop_table('partner_lab_tests')
    op.drop_table('partner_claim_events')
    op.drop_table('partner_claims')
    op.drop_table('partner_services')
    op.drop_table('partner_documents')
    op.drop_table('partner_lifecycle_events')
    op.drop_table('partner_profiles')
    op.drop_table('organization_members')
    op.drop_table('organizations')
