(function () {
  'use strict';

  angular.module('CyBorgBackup.pages.schedule')
    .controller('ScheduleAddCtrl', ScheduleAddCtrl);

  /** @ngInject */
  function ScheduleAddCtrl($rootScope, $scope, $filter, $uibModal, $state, $location, toastr, Prompt, Wait, Rest, ProcessErrors, ReturnToCaller, GetBasePath, QuerySet) {
    var defaultUrl = GetBasePath('schedules');

    $scope.schedule = {enabled: true};

    $scope.cronExpression = '0 8 9 9 1/8 ? *';
    $scope.cronOptions = {};
    $scope.isCronDisabled = false;

    init();
    function init(){
      $scope.isAddForm = true;
      Rest.setUrl(GetBasePath('schedules'));
      Rest.options()
          .then(({data}) => {
              if (!data.actions.POST) {
                  $state.go("^");
                  Alert('Permission Error', 'You do not have permission to add a schedule.', 'alert-info');
              }
          });
    }

    $scope.formCancel = function() {
        $state.go('schedule.list', null, { reload: true });
    };

    // Save
    $scope.formSave = function() {
        var fld, data = {};
        if (this.$ctrl.scheduleForm.$valid) {
            Rest.setUrl(defaultUrl);
            data = $scope.schedule;
            Wait('start');
            Rest.post(data)
                .then(({data}) => {
                    var base = $location.path().replace(/^\//, '').split('/')[0];
                    if (base === 'schedule') {
                        toastr.success("New schedule successfully created !", "New schedule");
                        $state.go('schedule.list', null, { reload: true });
                    } else {
                        ReturnToCaller(1);
                    }
                })
                .catch(({data, status}) => {
                    toastr.error('Failed to add new schedule. POST returned status: ' + status, "Error!");
                });
        }
    };

  }

})();
