# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.decorators import link, action
from rest_framework.reverse import reverse
from rest_framework.permissions import IsAuthenticated
from treeherder.model.derived import DatasetNotFoundError
from treeherder.webapp.api.utils import (UrlQueryFilter, with_jobs,
                                         oauth_required,
                                         to_timestamp)

PLATFORM_ORDER = {
    "linux32": 0,
    "linux64": 1,
    "osx-10-6": 2,
    "osx-10-8": 3,
    "osx-10-9": 4,
    "windowsxp": 5,
    "windows7-32": 6,
    "windows8-32": 7,
    "windows8-64": 8,
    "windows2012-64": 9,
    "android-2-2-armv6": 10,
    "android-2-2": 11,
    "android-2-3-armv6": 12,
    "android-2-3": 13,
    "android-2-3-armv7-api9": 14,
    "android-4-0": 15,
    "android-4-0-armv7-api10": 16,
    "android-4-0-armv7-api11": 17,
    "android-4-2-x86": 18,
    "b2g-linux32": 19,
    "b2g-linux64": 20,
    "b2g-osx": 21,
    "b2g-win32": 22,
    "b2g-emu-ics": 23,
    "b2g-emu-jb": 24,
    "b2g-emu-kk": 25,
    "b2g-device-image" : 26,
    "mulet-linux32" : 27,
    "mulet-linux64" : 28,
    "mulet-osx": 29,
    "mulet-win32": 30,
    "other": 31
}

OPT_ORDER = {
    "opt": 0,
    "pgo": 1,
    "asan": 2,
    "debug": 3,
    "cc": 4,
}


class ResultSetViewSet(viewsets.ViewSet):
    """
    View for ``resultset`` records

    ``result sets`` are synonymous with ``pushes`` in the ui
    """
    throttle_scope = 'resultset'

    @with_jobs
    def list(self, request, project, jm):
        """
        GET method for list of ``resultset`` records with revisions

        """
        # make a mutable copy of these params
        filter_params = request.QUERY_PARAMS.copy()

        # This will contain some meta data about the request and results
        meta = {}

        # support ranges for date as well as revisions(changes) like old tbpl
        for param in ["fromchange", "tochange", "startdate", "enddate"]:
            v = filter_params.get(param, None)
            if v:
                del(filter_params[param])
                meta[param] = v

        # translate these params into our own filtering mechanism
        if 'fromchange' in meta:
            filter_params.update({
                "push_timestamp__gte": jm.get_revision_timestamp(meta['fromchange'])
            })
        if 'tochange' in meta:
            filter_params.update({
                "push_timestamp__lte": jm.get_revision_timestamp(meta['tochange'])
            })
        if 'startdate' in meta:
            filter_params.update({
                "push_timestamp__gte": to_timestamp(meta['startdate'])
            })
        if 'enddate' in meta:

            # add a day because we aren't supplying a time, just a date.  So
            # we're doing ``less than``, rather than ``less than or equal to``.
            filter_params.update({
                "push_timestamp__lt": to_timestamp(meta['enddate']) + 86400
            })

        meta['filter_params'] = filter_params

        filter = UrlQueryFilter(filter_params)

        offset_id = filter.pop("id__lt", 0)
        count = min(int(filter.pop("count", 10)), 1000)

        full = filter.pop('full', 'true').lower() == 'true'

        objs = jm.get_result_set_list(
            offset_id,
            count,
            full,
            filter.conditions
            )

        for rs in objs:
            rs["revisions_uri"] = reverse("resultset-revisions",
                kwargs={"project": jm.project, "pk": rs["id"]})

            results = objs

        meta['count'] = len(results)
        meta['repository'] = project

        resp = {
            'meta': meta,
            'results': results,
            }

        return Response(resp)

    @with_jobs
    def retrieve(self, request, project, jm, pk=None):
        """
        GET method implementation for detail view of ``resultset``
        """
        filter = UrlQueryFilter({"id": pk})

        full = filter.pop('full', 'true').lower() == 'true'

        objs = jm.get_result_set_list(0, 1, full, filter.conditions)
        if objs:
            debug = request.QUERY_PARAMS.get('debug', None)
            rs = self.get_resultsets_with_jobs(jm, objs, full, {}, debug)
            return Response(rs[0])
        else:
            return Response("No resultset with id: {0}".format(pk), 404)

    @link()
    @with_jobs
    def revisions(self, request, project, jm, pk=None):
        """
        GET method for revisions of a resultset
        """
        objs = jm.get_resultset_revisions_list(pk)
        return Response(objs)


    @action(permission_classes=[IsAuthenticated])
    @with_jobs
    def cancel_all(self, request, project, jm, pk=None):
        """
        Cancel all pending and running jobs in this resultset
        """

        if not pk:  # pragma nocover
            return Response({"message": "resultset id required"}, status=400)

        try:
            jm.cancel_all_resultset_jobs(pk)
            return Response({"message": "pending and running jobs canceled for resultset '{0}'".format(pk)})

        except Exception as ex:
            return Response("Exception: {0}".format(ex), 404)

    @with_jobs
    @oauth_required
    def create(self, request, project, jm):
        """
        POST method implementation
        """
        try:
            jm.store_result_set_data(request.DATA)
        except DatasetNotFoundError as e:
            return Response({"message": str(e)}, status=404)
        except Exception as e:  # pragma nocover
            import traceback
            traceback.print_exc()
            return Response({"message": str(e)}, status=500)
        finally:
            jm.disconnect()

        return Response({"message": "well-formed JSON stored"})

