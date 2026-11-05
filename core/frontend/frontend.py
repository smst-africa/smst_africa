from dataclasses import dataclass
from backend.models import SmStNewsLetter
from django.db import transaction
@dataclass
class NewsLetterUser:
    email: str
    firstName: str
    lastName: str

class NewsLetterRepo:
    def check_newsletter_subscription(self, email):
        return SmStNewsLetter.objects.filter(email=email).exists()
    
    @transaction.atomic
    def create_newsletter_user(self, newsletter:NewsLetterUser) -> list:
        try:
            SmStNewsLetter.objects.get_or_create(
                email = newsletter.email,
                defaults = {
                    "first_name": newsletter.firstName,
                    "last_name": newsletter.lastName
                }
            )
            return True
        except:
            return False
    
    @transaction.atomic
    def remove_news_letter_user(self, email)->bool:
        user = SmStNewsLetter.objects.filter(
            email=email
        ).first()
        if user:
            user.delete()
            return True

class BaseNewsLetter:
    def __init__(self):
        self.repo = NewsLetterRepo()

class CreateNewsLetterUser(BaseNewsLetter):
    def execute(self, email, firstName, lastName):
        newsletter = NewsLetterUser(
            email = email,
            firstName= firstName,
            lastName=lastName
        )
        return self.repo.create_newsletter_user(newsletter)

def create_newsletter_user(email, firstName, lastName):
    return CreateNewsLetterUser().execute(email, firstName, lastName)

class RemoveNewsLetterUser(BaseNewsLetter):
    def execute(self, email):
        return self.repo.remove_news_letter_user(email)
    
def remove_news_letter_user(email):
    return RemoveNewsLetterUser().execute(email)

class CheckNewsletterSubscription(BaseNewsLetter):
    def execute(self, email):
        return self.repo.check_newsletter_subscription(email)
    
def check_newsletter_subscription(email):
    return CheckNewsletterSubscription().execute(email)