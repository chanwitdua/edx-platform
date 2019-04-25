"""
API Serializers
"""
from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator

from lms.djangoapps.program_enrollments.models import ProgramEnrollment

class ProgramEnrollmentSerializer(serializers.ModelSerializer):
    """
    Serializer for Program Enrollments
    """
  
    class Meta(object):
        model = ProgramEnrollment
        fields = ('user', 'external_user_key', 'program_uuid', 'curriculum_uuid', 'status')
        validators = []

    def validate(self, data):
        enrollment = ProgramEnrollment(**data)
        enrollment.full_clean()
        return data

    def create(self, validated_data):
        return ProgramEnrollment.objects.create(**validated_data)
