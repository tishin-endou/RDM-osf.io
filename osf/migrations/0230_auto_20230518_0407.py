# -*- coding: utf-8 -*-
# Generated by Django 1.11.28 on 2023-05-18 04:07
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('osf', '0229_loa'),
    ]

    operations = [
        migrations.AlterField(
            model_name='loa',
            name='aal',
            field=models.IntegerField(blank=True, choices=[(0, 'NULL'), (1, 'AAL1'), (2, 'AAL2')], null=True),
        ),
        migrations.AlterField(
            model_name='loa',
            name='ial',
            field=models.IntegerField(blank=True, choices=[(0, 'NULL'), (1, 'IAL1'), (2, 'IAL2')], null=True),
        ),
    ]