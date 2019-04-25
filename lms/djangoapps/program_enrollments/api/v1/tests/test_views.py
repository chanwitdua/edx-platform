"""
Unit tests for ProgramEnrollment views.
"""
from __future__ import unicode_literals

import json

from uuid import uuid4

from django.urls import reverse
from rest_framework.test import APITestCase

from lms.djangoapps.program_enrollments.models import ProgramEnrollment


class ProgramEnrollmentViewTests(APITestCase):
    """
    Tests for the ProgramEnrollment view.
    """

    def test_post_one_enrollment(self):
        program_key = uuid4()
        statuses = ['pending', 'enrolled', 'pending']
        external_user_keys = ['abc1', 'efg2', 'hij3']

        curriculum_uuid = uuid4()
        curriculum_uuids = [curriculum_uuid, curriculum_uuid, uuid4()]
        post_data = [
            {
                'external_user_key': e,
                'status': s,
                'curriculum_uuid': str(c)
            } 
            for e, s, c in zip(external_user_keys, statuses, curriculum_uuids)
        ]

        self.url = reverse('programs_api:v1:program_enrollments', args=[program_key])


        response = self.client.post(self.url, json.dumps(post_data), content_type='application/json')
        self.assertEqual(response.status_code, 201)

        enrollments = ProgramEnrollment.objects.all()
        for i in range(3):
            actual_program_uuid = enrollments[i].program_uuid
            actual_external_user_key = enrollments[i].external_user_key
            actual_status = enrollments[i].status
            actual_curriculum_uuid = enrollments[i].curriculum_uuid

            self.assertEqual(actual_program_uuid, program_key)
            self.assertEqual(actual_external_user_key, external_user_keys[i])
            self.assertEqual(actual_status, statuses[i])
            self.assertEqual(actual_curriculum_uuid, curriculum_uuids[i])
    
    def test_enrollment_payload_limit(self):
        def student_enrollment(status):
            return {
                'status': status,
                'external_user_key': str(uuid4().hex[0:10]),
                'curriculum_uuid': str(uuid4())
            }
        post_data = []
        for i in range(26):
            post_data += student_enrollment('enrolled')

        self.url = reverse('programs_api:v1:program_enrollments', args=[uuid4()])
        response = self.client.post(self.url, json.dumps(post_data), content_type='application/json')
        self.assertEqual(response.status_code, 413)
