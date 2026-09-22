"""Phase 6: family accounts & caregiver access

Revision ID: 3f8a91c4d7e2
Revises: 00e49dc73a52
Create Date: 2026-09-20

Additive only: two new tables + one nullable column on appointments.
No Phase 1-5 table is altered destructively; nothing cascades into
patient medical data.
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = '3f8a91c4d7e2'
down_revision = '00e49dc73a52'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'family_relationships',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('owner_user_id', sa.String(length=36), nullable=False),
        sa.Column('member_user_id', sa.String(length=36), nullable=True),
        sa.Column('display_name', sa.String(length=120), nullable=False),
        sa.Column('relationship_type', sa.String(length=40), nullable=False),
        sa.Column('invited_email', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('invitation_token_hash', sa.String(length=64), nullable=False),
        sa.Column('invitation_expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('declined_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], name='fk_family_rel_owner'),
        sa.ForeignKeyConstraint(['member_user_id'], ['users.id'], name='fk_family_rel_member'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_family_rel_owner', 'family_relationships', ['owner_user_id'])
    op.create_index('ix_family_rel_member', 'family_relationships', ['member_user_id'])
    op.create_index('ix_family_rel_status', 'family_relationships', ['status'])
    op.create_index('ix_family_token_hash', 'family_relationships', ['invitation_token_hash'])
    op.create_index(
        'uq_family_active_relationship',
        'family_relationships',
        ['owner_user_id', 'member_user_id'],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
        sqlite_where=sa.text("status = 'ACTIVE'"),
    )

    op.create_table(
        'family_access_consents',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('relationship_id', sa.String(length=36), nullable=False),
        sa.Column('scopes', sa.String(length=300), nullable=False),
        sa.Column('category_filter', sa.String(length=300), nullable=False),
        sa.Column('purpose', sa.Text(), nullable=False),
        sa.Column('granted_by', sa.String(length=36), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['relationship_id'], ['family_relationships.id'], name='fk_family_consent_rel'
        ),
        sa.ForeignKeyConstraint(['granted_by'], ['users.id'], name='fk_family_consent_granter'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_family_consent_rel', 'family_access_consents', ['relationship_id'])

    # Phase 6: appointment actor separation (NULL = self-booked).
    # Batch mode: SQLite cannot ALTER constraints in place; batch recreates
    # the table there and passes through as plain ALTER on PostgreSQL.
    with op.batch_alter_table('appointments') as batch:
        batch.add_column(sa.Column('requested_by_user_id', sa.String(length=36), nullable=True))
        batch.create_foreign_key(
            'fk_appointments_requested_by',
            'users',
            ['requested_by_user_id'],
            ['id'],
        )


def downgrade() -> None:
    with op.batch_alter_table('appointments') as batch:
        batch.drop_constraint('fk_appointments_requested_by', type_='foreignkey')
        batch.drop_column('requested_by_user_id')
    op.drop_index('ix_family_consent_rel', table_name='family_access_consents')
    op.drop_table('family_access_consents')
    op.drop_index('ix_family_token_hash', table_name='family_relationships')
    op.drop_index('uq_family_active_relationship', table_name='family_relationships')
    op.drop_index('ix_family_rel_status', table_name='family_relationships')
    op.drop_index('ix_family_rel_member', table_name='family_relationships')
    op.drop_index('ix_family_rel_owner', table_name='family_relationships')
    op.drop_table('family_relationships')
