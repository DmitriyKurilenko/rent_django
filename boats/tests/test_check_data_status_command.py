from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase


class CheckDataStatusCommandTest(TestCase):
    def test_check_data_status_uses_role_ref_and_runs(self):
        manager = User.objects.create_user(username='manager_cmd', password='pass123')
        manager.profile.role = 'manager'
        manager.profile.save(update_fields=['role_ref'])

        out = StringIO()
        call_command('check_data_status', stdout=out)

        output = out.getvalue()
        self.assertIn('ПОЛЬЗОВАТЕЛИ', output)
        self.assertIn('Менеджер', output)
