"""Notebooks, their cells and their runs.

The provenance third of the split store. A notebook's *displayed* output goes
to query_results as today, its *handoff* between cells goes to a file the
notebook owns -- arbitrary rows, disposable, re-materialized by re-running --
and what is here is the small part that is kept for ever: which cell ran,
when, reading which other cells, and what it cost.

That third is what makes staleness answerable. A cell whose inputs have
re-run since can say so before anybody trusts its number, which is the one
thing Zeppelin never had and the reason Zeppelin notebooks rot.

Revision ID: 073f8bb38e7a
Revises: f3a71c20e9d5
Create Date: 2026-10-29 18:03:10.479510

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '073f8bb38e7a'
down_revision = 'f3a71c20e9d5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('notebooks',
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('org_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('description', sa.String(length=4096), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('is_archived', sa.Boolean(), nullable=False),
    sa.Column('is_draft', sa.Boolean(), nullable=False),
    sa.Column('options', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_notebooks_is_archived'), 'notebooks', ['is_archived'], unique=False)
    op.create_index(op.f('ix_notebooks_is_draft'), 'notebooks', ['is_draft'], unique=False)
    op.create_table('notebook_cells',
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('notebook_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('source', sa.Text(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('data_source_id', sa.Integer(), nullable=True),
    sa.Column('latest_result_id', sa.Integer(), nullable=True),
    sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('options', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.ForeignKeyConstraint(['data_source_id'], ['data_sources.id'], ),
    sa.ForeignKeyConstraint(['latest_result_id'], ['query_results.id'], ),
    sa.ForeignKeyConstraint(['notebook_id'], ['notebooks.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('notebook_id', 'name', name='unique_cell_name_in_notebook')
    )
    op.create_index(op.f('ix_notebook_cells_notebook_id'), 'notebook_cells', ['notebook_id'], unique=False)
    op.create_table('notebook_runs',
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('notebook_id', sa.Integer(), nullable=False),
    sa.Column('cell_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('state', sa.String(length=32), nullable=False),
    sa.Column('inputs', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('runtime', sa.Float(), nullable=True),
    sa.Column('rows', sa.Integer(), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['cell_id'], ['notebook_cells.id'], ),
    sa.ForeignKeyConstraint(['notebook_id'], ['notebooks.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_notebook_runs_cell_id'), 'notebook_runs', ['cell_id'], unique=False)
    op.create_index(op.f('ix_notebook_runs_notebook_id'), 'notebook_runs', ['notebook_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_notebook_runs_notebook_id'), table_name='notebook_runs')
    op.drop_index(op.f('ix_notebook_runs_cell_id'), table_name='notebook_runs')
    op.drop_table('notebook_runs')
    op.drop_index(op.f('ix_notebook_cells_notebook_id'), table_name='notebook_cells')
    op.drop_table('notebook_cells')
    op.drop_index(op.f('ix_notebooks_is_draft'), table_name='notebooks')
    op.drop_index(op.f('ix_notebooks_is_archived'), table_name='notebooks')
    op.drop_table('notebooks')
