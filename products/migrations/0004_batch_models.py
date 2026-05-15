# Hand-written migration for Requirement 4 (Batch Processing).
# If `python manage.py makemigrations products` is run, Django will
# detect that this migration already exists and skip regeneration.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0003_wallet'),
    ]

    operations = [
        migrations.CreateModel(
            name='DailySalesReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('report_date', models.DateField(db_index=True, unique=True)),
                ('total_orders', models.IntegerField(default=0)),
                ('total_items_sold', models.IntegerField(default=0)),
                ('total_revenue', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('product_breakdown', models.JSONField(blank=True, default=dict)),
                ('generated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['-report_date']},
        ),
        migrations.CreateModel(
            name='BatchJobLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('job_name', models.CharField(db_index=True, max_length=100)),
                ('mode', models.CharField(default='chunked', max_length=20)),
                ('chunk_size', models.IntegerField(blank=True, null=True)),
                ('total_records', models.IntegerField(default=0)),
                ('started_at', models.DateTimeField(auto_now_add=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('duration_seconds', models.FloatField(blank=True, null=True)),
                ('status', models.CharField(
                    choices=[('RUNNING', 'Running'), ('SUCCESS', 'Success'), ('FAILED', 'Failed')],
                    default='RUNNING', max_length=20,
                )),
                ('error_message', models.TextField(blank=True, default='')),
                ('metadata', models.JSONField(blank=True, default=dict)),
            ],
            options={'ordering': ['-started_at']},
        ),
    ]
