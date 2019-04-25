# -*- coding: utf-8 -*-
"""
ProgramEnrollment Views
"""
from __future__ import unicode_literals

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from lms.djangoapps.program_enrollments.api.v1.serializers import ProgramEnrollmentSerializer

class ProgramEnrollmentsView(APIView):
    """
    POST view for ProgramEnrollments
    """

    def post(self, request, *args, **kwargs):
        if len(request.data) > 25:
            return Response(
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                content_type='application/json',
            )

        for d in request.data:
            data = {key: value for key, value in d.items()}
            data['program_uuid'] = kwargs['program_key']
            serializer = ProgramEnrollmentSerializer(data=data)

            if serializer.is_valid(raise_exception=True):
                serializer.save()  # can also raise ValidationError

        return Response(
                    status=status.HTTP_201_CREATED,
                    content_type='application/json',
                )