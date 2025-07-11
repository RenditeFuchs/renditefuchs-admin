# Generated by Django 5.2.3 on 2025-07-02 16:27

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('monitoring', '0002_alter_alert_options_alter_errorlog_options_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='platform',
            name='color',
            field=models.CharField(choices=[('success', 'Grün (Live)'), ('warning', 'Orange (Test)'), ('secondary', 'Grau (Inaktiv)')], default='info', max_length=15),
        ),
        migrations.AlterField(
            model_name='platform',
            name='environment',
            field=models.CharField(choices=[('test', 'Test'), ('live', 'Live')], default='test', max_length=10),
        ),
    ]
