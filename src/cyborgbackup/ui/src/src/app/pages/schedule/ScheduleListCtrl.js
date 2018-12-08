(function () {
  'use strict';

  angular.module('CyBorgBackup.pages.schedule')
    .controller('ScheduleListCtrl', ScheduleListCtrl);

  /** @ngInject */
  function ScheduleListCtrl($scope, $filter, $uibModal, $state, toastr, Prompt, Wait, Rest, ProcessErrors, GetBasePath, QuerySet) {
    $scope.tablePageSize = 10;
    let path = GetBasePath('schedules');

    $scope.pipeCall = function(tableState){
      var pagination = tableState.pagination;
      var start = pagination.start || 0;
      var number = pagination.number || 25;

      QuerySet.search(path+'?page_size='+number+'&page='+((start/number)+1)).then(function(data){
         var results = data.data.results;
         tableState.pagination.numberOfPages = Math.ceil(data.data.count/tableState.pagination.number);
         $scope.schedules = results;
      });
    };

    $scope.switchState = function(item) {
      var id = item.id;
      var name = item.name;
      var data={};
      Wait('start');
      var url = path + id + '/';
      Rest.setUrl(url);
      data['enabled'] = !item.enabled;
      Rest.patch(data)
          .then(() => {
              item.enabled = data['enabled'];
          })
          .catch(({data, status}) => {
              toastr.error('Failed to change state '+name+'. ' + data.detail, "Error!");
          });
    };

    $scope.addItem = function() {
        $state.go('schedule.add');
    };

    $scope.editItem = function(item) {
        $state.go('schedule.edit', { schedule_id: item.id });
    };

    $scope.removeItem = function(item) {
      var id = item.id;
      var name = item.name;
      var action = function() {
          $('#prompt-modal').modal('hide');
          Wait('start');
          var url = path + id + '/';
          Rest.setUrl(url);
          Rest.destroy()
              .then(() => {

                  let reloadListStateParams = null;

                  if($scope.schedules.length === 1 && $state.params.schedule_search && !_.isEmpty($state.params.schedule_search.page) && $state.params.schedule_search.page !== '1') {
                      reloadListStateParams = _.cloneDeep($state.params);
                      reloadListStateParams.schedule_search.page = (parseInt(reloadListStateParams.schedule_search.page)-1).toString();
                  }

                  if (parseInt($state.params.schedule_id) === id) {
                      $state.go('^', null, { reload: true });
                  } else {
                      $state.go('.', null, { reload: true });
                  }
              })
              .catch(({data, status}) => {
                  toastr.error('Failed to delete '+name+'. ' + data.detail, "Error!");
              });
      };

      Prompt({
          hdr: 'Delete',
          resourceName: $filter('sanitize')(name),
          body: '<div class="Prompt-bodyQuery">Are you sure you want to delete this schedule ?</div>',
          action: action,
          actionText: 'Delete'
      });
    }
  }

})();
