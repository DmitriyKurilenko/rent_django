from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from accounts.models import UserProfile


TEST_USERS = [
    {
        "username": "manager1",
        "password": "Kapitan123",
        "email": "manager1@example.com",
        "role": "manager",
        "is_staff": True,
        "is_superuser": False,
        "subscription_plan": "advanced",
    },
    {
        "username": "manager2",
        "password": "Kapitan123",
        "email": "manager2@example.com",
        "role": "manager",
        "is_staff": True,
        "is_superuser": False,
        "subscription_plan": "advanced",
    },
    {
        "username": "captain1",
        "password": "Kapitan123",
        "email": "captain1@example.com",
        "role": "captain",
        "is_staff": False,
        "is_superuser": False,
        "subscription_plan": "standard",
    },
    {
        "username": "captain2",
        "password": "Kapitan123",
        "email": "captain2@example.com",
        "role": "captain",
        "is_staff": False,
        "is_superuser": False,
        "subscription_plan": "standard",
    },
    {
        "username": "tourist1",
        "password": "Kapitan123",
        "email": "tourist1@example.com",
        "role": "tourist",
        "is_staff": False,
        "is_superuser": False,
        "subscription_plan": "free",
    },
    {
        "username": "tourist2",
        "password": "Kapitan123",
        "email": "tourist2@example.com",
        "role": "tourist",
        "is_staff": False,
        "is_superuser": False,
        "subscription_plan": "free",
    },
    {
        "username": "superadmin",
        "password": "Kapitan123",
        "email": "superadmin@example.com",
        "role": "superadmin",
        "is_staff": True,
        "is_superuser": True,
        "subscription_plan": "advanced",
    },
]


class Command(BaseCommand):
    help = "Create or update predefined test users"

    def add_arguments(self, parser):
        parser.add_argument(
            "--show-passwords",
            action="store_true",
            help="Print test user passwords in output",
        )

    def handle(self, *args, **options):
        show_passwords = options["show_passwords"]

        self.stdout.write(self.style.NOTICE("=== CREATE/UPDATE TEST USERS ==="))

        for user_data in TEST_USERS:
            user, created = User.objects.get_or_create(
                username=user_data["username"],
                defaults={
                    "email": user_data["email"],
                    "is_staff": user_data["is_staff"],
                    "is_superuser": user_data["is_superuser"],
                },
            )

            user.email = user_data["email"]
            user.is_staff = user_data["is_staff"]
            user.is_superuser = user_data["is_superuser"]
            user.set_password(user_data["password"])
            user.save(update_fields=["email", "is_staff", "is_superuser", "password"])

            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.subscription_plan = user_data["subscription_plan"]
            profile.role = user_data["role"]
            profile.save(update_fields=["subscription_plan", "role"])

            action = "Created" if created else "Updated"
            self.stdout.write(
                self.style.SUCCESS(
                    f"{action}: {user.username} | role={profile.role} | "
                    f"staff={user.is_staff} | superuser={user.is_superuser}"
                )
            )

        self.stdout.write(self.style.NOTICE("\n=== ROLE STATS ==="))
        for role_code, role_name in UserProfile.ROLE_CHOICES:
            count = UserProfile.objects.filter(role=role_code).count()
            self.stdout.write(f"{role_name}: {count}")

        self.stdout.write(self.style.NOTICE("\n=== TEST ACCOUNTS ==="))
        for item in TEST_USERS:
            line = f"{item['username']:15} | role={item['role']}"
            if show_passwords:
                line = f"{line} | password={item['password']}"
            self.stdout.write(line)

        self.stdout.write(self.style.SUCCESS("\nDone."))
