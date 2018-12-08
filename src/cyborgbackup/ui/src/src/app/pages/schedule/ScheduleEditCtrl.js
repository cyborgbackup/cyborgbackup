(function () {
  'use strict';

  angular.module('CyBorgBackup.pages.schedule')
    .controller('ScheduleEditCtrl', ScheduleEditCtrl);

  /** @ngInject */
  function ScheduleEditCtrl($rootScope, $scope, $filter, $uibModal, $state, $stateParams, toastr, Prompt, Wait, Rest, ProcessErrors, GetBasePath, QuerySet) {
    var id = $stateParams.schedule_id,
    defaultUrl = GetBasePath('schedules') + id;

    $scope.cronExpression = '0 8 9 9 1/8 ? *';
    $scope.cronOptions = {};
    $scope.isCronDisabled = false;

    init();
    function init() {
        Rest.setUrl(defaultUrl);
        Wait('start');
        Rest.get(defaultUrl).then(({data}) => {
                $scope.schedule_id = id;

                $scope.schedule_obj = data;
                $scope.schedule = data;
                $scope.name = data.name;

                //setScopeFields(data);
                Wait('stop');
            })
            .catch(({data, status}) => {
                toastr.error('Failed to retrieve schedule: '+$stateParams.id+'. GET status: ' + status, "Error!");
            });
    }

    $scope.formCancel = function() {
        $state.go('schedule.list', null, { reload: true });
    };

    $scope.formSave = function() {
        $rootScope.flashMessage = null;
        if (this.$ctrl.scheduleForm.$valid) {
            Rest.setUrl(defaultUrl + '/');
            var data = $scope.schedule;
            Rest.put(data).then(() => {
                toastr.success("Schedule "+$scope.schedule.name+" successfully updated !", "Update schedule");
                $state.go('schedule.list', null, { reload: true });
            })
            .catch(({data, status}) => {
                toastr.error('Failed to update schedule: '+$stateParams.id+'. GET status: ' + status, "Error!");
            });
        }
    };
  }

})();
