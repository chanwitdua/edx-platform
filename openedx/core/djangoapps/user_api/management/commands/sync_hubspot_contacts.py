"""
Management command to sync platform users with hubspot
./manage.py lms sync_hubspot_contacts
./manage.py lms sync_hubspot_contacts --initial-sync-days=7 --batch-size=20
"""
import json
import time
import traceback
import urlparse
from datetime import datetime, timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.utils.html import escapejs

from edx_rest_api_client.client import EdxRestApiClient
from slumber.exceptions import HttpClientError, HttpServerError

from openedx.core.djangoapps.site_configuration.models import SiteConfiguration
from student.models import UserAttribute, UserProfile
from util.query import use_read_replica_if_available

HUBSPOT_API_BASE_URL = 'https://api.hubapi.com'


class Command(BaseCommand):
    """
    Command to create contacts in hubspot for those partner who has enabled hubspot integration.
    This command is suppose to sync contact with hubspot on daily basis.
    """

    def _get_hubspot_enabled_sites(self):
        """
        Returns: list of site configurations having hubspot integration enabled
        """
        site_confs = SiteConfiguration.objects.all()
        hubspot_sites = [
            site_conf for site_conf in site_confs
            if site_conf.get_value('HUBSPOT_API_KEY')
        ]
        return hubspot_sites

    def _get_users_queryset(self, initial_days):
        """
        initial_days: numbers of days to go back from today
        :return: users queryset
        """
        start_date = datetime.now().date() - timedelta(initial_days)
        end_date = datetime.now().date() - timedelta(1)
        if start_date == end_date:
            self.stdout.write(u'Getting users on={date}'.format(date=start_date))
            return User.objects.filter(date_joined__date=start_date)
        self.stdout.write(u'Getting users from {start} to {end}'.format(start=start_date, end=end_date))
        return User.objects.filter(date_joined__date__gte=start_date, date_joined__date__lte=end_date)

    def _get_batched_users(self, site_domain, users_queryset, offset, users_query_batch_size):
        """
        Args:
            site_domain: site where we need unsynced users
            users_queryset: users_queryset to slice
            users_query_batch_size: slice size

        Returns: site users

        """

        self.stdout.write(
            u'Fetching Users for site {site} from {start} to {end}'.format(
                site=site_domain, start=offset, end=offset + users_query_batch_size
            )
        )
        users = users_queryset.select_related('profile')[offset: offset + users_query_batch_size]
        site_users = [
            user for user in use_read_replica_if_available(users)
            if UserAttribute.get_user_attribute(user, 'created_on_site') == site_domain
        ]
        self.stdout.write(u'\tSite Users={count}'.format(count=len(site_users)))

        return site_users

    def _get_level_of_education_display(self, loe):
        """
        Returns: Descriptive level of education
        """
        level_of_education = ''
        for _loe in UserProfile.LEVEL_OF_EDUCATION_CHOICES:
            if loe == _loe[0]:
                level_of_education = _loe[1]
        return level_of_education

    def _escape_json(self, value):
        """
        Escapes js for now. Additional escaping can be done here.
        """
        return escapejs(value)

    def _sync_with_hubspot(self, users_batch, site_conf):
        """
        Sync batch of users with hubspot
        """
        contacts = []
        for user in users_batch:
            if not hasattr(user, 'profile'):
                self.stdout.write(u'skipping user {} due to no profile found'.format(user))
                continue
            if not user.profile.meta:
                self.stdout.write(u'skipping user {} due to no profile meta found'.format(user))
                continue
            meta = json.loads(user.profile.meta)
            contact = {
                "email": user.email,
                "properties": [
                    {
                        "property": "firstname",
                        "value": self._escape_json(meta.get('first_name', ''))
                    },
                    {
                        "property": "lastname",
                        "value": self._escape_json(meta.get('last_name', ''))
                    },
                    {
                        "property": "company",
                        "value": self._escape_json(meta.get('company', ''))
                    },
                    {
                        "property": "jobtitle",
                        "value": self._escape_json(meta.get('title', ''))
                    },
                    {
                        "property": "state",
                        "value": self._escape_json(meta.get('state', ''))
                    },
                    {
                        "property": "country",
                        "value": self._escape_json(meta.get('country', ''))
                    },
                    {
                        "property": "gender",
                        "value": self._escape_json(user.profile.gender)
                    },
                    {
                        "property": "degree",
                        "value": self._escape_json(
                            self._get_level_of_education_display(user.profile.level_of_education)
                        )
                    },
                ]
            }
            contacts.append(contact)

        api_key = site_conf.get_value('HUBSPOT_API_KEY')
        client = EdxRestApiClient(urlparse.urljoin(HUBSPOT_API_BASE_URL, 'contacts/v1/contact'))
        try:
            client.batch.post(contacts, hapikey=api_key)
            return len(contacts)
        except (HttpClientError, HttpServerError) as ex:
            message = u'An error occurred while syncing batch of contacts for site {domain}, {message}'.format(
                domain=site_conf.site.domain, message=ex.message
            )
            self.stderr.write(message)
            return 0

    def _sync_site(self, site_conf, users_queryset, users_count, contacts_batch_size):
        """
            Syncs a single site
        """
        site_domain = site_conf.site.domain
        self.stdout.write(u'Syncing process started for site {site}'.format(site=site_domain))

        offset = 0
        users_queue = []
        users_query_batch_size = 1000
        successfully_synced_contacts = 0

        while offset < users_count:
            is_last_iteration = (offset + users_query_batch_size) >= users_count
            self.stdout.write(
                u'Syncing users batch from {start} to {end} for site {site}'.format(
                    start=offset, end=offset + users_query_batch_size, site=site_domain
                )
            )
            users_queue += self._get_batched_users(site_domain, users_queryset, offset, users_query_batch_size)
            while len(users_queue) >= contacts_batch_size \
                    or (is_last_iteration and users_queue):  # for last iteration need to empty users_queue
                users_batch = users_queue[:contacts_batch_size]
                del users_queue[:contacts_batch_size]
                successfully_synced_contacts += self._sync_with_hubspot(users_batch, site_conf)
                time.sleep(0.1)  # to make sure request per second could not exceed by 10
            self.stdout.write(
                u'Successfully synced users batch from {start} to {end} for site {site}'.format(
                    start=offset, end=offset + users_query_batch_size, site=site_domain
                )
            )
            offset += users_query_batch_size

        self.stdout.write(
            u'{count} contacts found and sycned for site {site}'.format(
                count=successfully_synced_contacts, site=site_domain
            )
        )

    def add_arguments(self, parser):
        """
        Definition of arguments this command accepts
        """
        parser.add_argument(
            '--initial-sync-days',
            default=1,
            dest='initial_sync_days',
            type=int,
            help='Number of days before today to start sync',
        )
        parser.add_argument(
            '--batch-size',
            default=100,
            dest='batch_size',
            type=int,
            help='Size of contacts batch to be sent to hubspot',
        )

    def handle(self, *args, **options):
        """
        Main command handler
        """
        initial_sync_days = options['initial_sync_days']
        batch_size = options['batch_size']
        try:
            self.stdout.write(u'Command execution started with options = {}.'.format(options))
            hubspot_sites = self._get_hubspot_enabled_sites()
            self.stdout.write(u'{count} hubspot enabled sites found.'.format(count=len(hubspot_sites)))

            users_queryset = self._get_users_queryset(initial_sync_days)
            users_count = users_queryset.count()
            self.stdout.write(u'Users count={count}'.format(count=users_count))
            for site_conf in hubspot_sites:
                self._sync_site(site_conf, users_queryset, users_count, batch_size)

        except Exception as ex:
            traceback.print_exc()
            raise CommandError(u'Command failed with traceback %s' % str(ex))
