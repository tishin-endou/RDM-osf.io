# -*- coding: utf-8 -*-
# Generated by Django 1.11.28 on 2022-02-17 14:10
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('osf', '0218_ensure_reports'),
    ]

    operations = [
        migrations.AddField(
            model_name='osfuser',
            name='temp_account',
            field=models.BooleanField(default=False),
        ),
    ]