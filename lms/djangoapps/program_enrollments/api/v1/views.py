# -*- coding: utf-8 -*-
"""
ProgramEnrollment Views
"""
from __future__ import unicode_literals

from collections import OrderedDict

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from lms.djangoapps.program_enrollments.api.v1.serializers import ProgramEnrollmentSerializer
from lms.djangoapps.program_enrollments.models import ProgramEnrollment

class ProgramEnrollmentsView(APIView):
    """
    POST view for ProgramEnrollments
    """
    ERROR_CONFLICT = 'conflict'
    ERROR_DUPLICATED = 'duplicated'
    ERROR_INVALID_STATUS = 'invalid-status'

    def post(self, request, *args, **kwargs):
        if len(request.data) > 25:
            return Response(
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                content_type='application/json',
            )

        program_uuid = kwargs['program_key']
        student_data = OrderedDict((
            row['external_user_key'],
            {
                'program_uuid': program_uuid,
                'curriculum_uuid': row.get('curriculum_uuid'),
                'status': row.get('status'),
                'external_user_key': row.get('external_user_key'),
            })
            for row in request.data
        )

        existing_enrollments = ProgramEnrollment.bulk_read_by_student_key(program_uuid, student_data)

        response_data = {}
        for enrollment in existing_enrollments:
            response_data[enrollment.external_user_key] = self.ERROR_CONFLICT
            student_data.pop(enrollment.external_user_key)

        enrollments_to_create = {}

        for student_key, data in student_data.items():
            curriculum_uuid = data['curriculum_uuid']
            if (student_key, curriculum_uuid) in enrollments_to_create:
                response_data[student_key] = self.ERROR_DUPLICATED
                continue

            serializer = ProgramEnrollmentSerializer(data=data)

            if serializer.is_valid():
                enrollments_to_create[(student_key, curriculum_uuid)] = serializer
            else:
                if ('status' in serializer.errors and serializer.errors['status'][0].code == 'invalid_choice'):
                    response_data[student_key] = self.ERROR_INVALID_STATUS
                else:
                    return Response(
                        'invalid enrollment record',
                        HTTP_422_UNPROCESSABLE_ENTITY
                    )

        for enrollment_serializer in enrollments_to_create.values():
            # create the model
            enrollment_serializer.save()
            # TODO: make this a bulk save

        if not enrollments_to_create:
            return Response(
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                data=response_data,
                content_type='application/json',
            )

        if len(request.data) != len(enrolled_students):
            return Response(
                status=status.HTTP_207_MULTI_STATUS,
                data=response_data,
                content_type='application/json',
            )

        return Response(
            status=status.HTTP_201_CREATED,
            data=response_data,
            content_type='application/json',
        )
