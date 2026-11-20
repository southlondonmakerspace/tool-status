from django.db import models

# Create your models here.
class Tool(models.Model):
    name = models.CharField(max_length=50, primary_key=True)
    description = models.CharField(max_length=200,null=True,blank=True)
    functional = models.BooleanField()
    last_maintained = models.DateField(null = True, blank = True)
    maintenance_interval = models.IntegerField(null = True, blank = True)
    latest_issue = models.TextField(null = True, blank = True)

    def __str__(self):
        return f"{self.name}"

