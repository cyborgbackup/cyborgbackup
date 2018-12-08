(function () {
  'use strict';

  angular.module('CyBorgBackup.pages.job', [])
      .config(routeConfig);

  const defaultParams = {
        page_size: "200",
        order_by: 'start_line',
        not__event__in: 'playbook_on_start,playbook_on_play_start,playbook_on_task_start,playbook_on_stats'
    };

  /** @ngInject */
  function routeConfig(stateExtenderProvider) {
    stateExtenderProvider.$get()
        .addState({
          name: 'job',
          title: 'Jobs',
          url: '/job',
          templateUrl : 'app/pages/job/job.html',
          controller: 'JobListCtrl',
          data: {
                socket: {
                    groups: {
                        jobs: ['status_changed'],
                    }
                }
            },
          sidebarMeta: {
            icon: 'ion-gear-a',
            order: 1,
          },
        });
    stateExtenderProvider.$get()
        .addState({
          name: 'jobdetails',
          url: '/job/details/:id',
          title: 'Job Details',
          templateUrl: 'app/pages/job/details.html',
          controller: 'JobDetailCtrl',
          data: {
                socket: {
                    "groups": {
                        "jobs": ["status_changed", "summary"],
                        "job_events": []
                    }
                }
            },
          resolve: {
            statusSocket: ['$rootScope', '$stateParams', function($rootScope, $stateParams) {
                var preScope = {};
                var eventOn = $rootScope.$on(`ws-jobs`, function(e, data) {
                    if (parseInt(data.job_id, 10) ===
                        parseInt($stateParams.id,10)) {
                        preScope.job_status = data.status;
                    }
                });
                return [preScope, eventOn];
            }],
            Dataset: ['QuerySet', '$stateParams', 'jobData',
                        function(qs, $stateParams, jobData) {
                            let path = jobData.related.job_events;
                            return qs.search(path, $stateParams[`job_event_search`]);
                        }
                    ],
            // the GET for the particular job
            jobData: ['jobResults', '$stateParams', function(jobResults, $stateParams) {
                return jobResults.getJobData($stateParams.id);
            }],
            jobFinished: ['jobData', function(jobData) {
                if (jobData.finished) {
                    return true;
                } else {
                    return false;
                }
            }],
            jobDataOptions: ['Rest', 'GetBasePath', '$stateParams', '$q', function(Rest, GetBasePath, $stateParams, $q) {
                Rest.setUrl(GetBasePath('jobs') + $stateParams.id);
                var val = $q.defer();
                Rest.options()
                    .then(function(data) {
                        val.resolve(data.data);
                    }, function(data) {
                        val.reject(data);
                    });
                return val.promise;
            }],
          }
        });
  }

})();
