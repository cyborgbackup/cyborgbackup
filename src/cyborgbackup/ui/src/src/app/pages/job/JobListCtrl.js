(function () {
  'use strict';

  angular.module('CyBorgBackup.pages.job')
    .controller('JobListCtrl', JobListCtrl);

  /** @ngInject */
  function JobListCtrl($scope, $filter, $uibModal, $state, $interpolate, toastr, Prompt, Wait, Rest, ProcessErrors, GetBasePath, QuerySet) {
    $scope.tablePageSize = 10;
    let path = GetBasePath('jobs');
    let interpolator = $interpolate(path);

    $scope.initTable = false;

    $scope.listJobStatus = [
        {label: 'New', value: 'new'},
        {label: 'Running', value: 'running'},
        {label: 'Failed', value: 'failed'},
        {label: 'Successful', value: 'successful'},
        {label: 'Error', value: 'error'},
        {label: 'Canceled', value: 'canceled'},
        {label: 'Waiting', value: 'waiting'},
        {label: 'Pending', value: 'pending'}
    ];
    $scope.jobStatusSelected = {selected: $scope.listJobStatus};

    $scope.pipeCall = function(tableState){
      var pagination = tableState.pagination;
      var start = pagination.start || 0;
      var number = pagination.number || 25;

      var computeStatus = [];
      $scope.jobStatusSelected.selected.forEach(v => {
        computeStatus.push(v.value);
      });

      QuerySet.search(path+'?status__in='+computeStatus.join(',')+'&page_size='+number+'&page='+((start/number)+1)).then(function(data){
         var results = data.data.results;
         tableState.pagination.numberOfPages = Math.ceil(data.data.count/tableState.pagination.number);
         $scope.jobs = results;
         $scope.initTable = true;
      });
    };

    $scope.$watch('jobStatusSelected.selected', function(){
        if( $scope.initTable ) {
            var tableState = $('#jobTable').data().$stTableController.tableState();
            var pagination = tableState.pagination;
            var start = pagination.start || 0;
            var number = pagination.number || 25;

            var computeStatus = [];
            $scope.jobStatusSelected.selected.forEach(v => {
                computeStatus.push(v.value);
            });

            QuerySet.search(path + '?status__in=' + computeStatus.join(',') + '&page_size=' + number + '&page=' + ((start / number) + 1)).then(function (data) {
                var results = data.data.results;
                tableState.pagination.numberOfPages = Math.ceil(data.data.count / tableState.pagination.number);
                $scope.jobs = results;
            });
        }
    });


    $scope.viewJobResults = function(job) {
      $state.go('jobdetails', { id: job.id}, { reload: true});
    };

    $scope.$on('ws-jobs', function(){
        let path;
        if (GetBasePath(path) || GetBasePath('jobs')) {
            path = GetBasePath(path) || GetBasePath('jobs');
        } else {
            // completed jobs base path involves $stateParams
            let interpolator = $interpolate(path);
            path = interpolator({ $rootScope: $rootScope, $stateParams: $stateParams });
        }
        QuerySet.search(path, [])
        .then(function(searchResponse) {
            $scope['jobs'] = searchResponse.data.results;
        });
    });
    $scope.$on('ws-schedules', function(){
        $state.reload();
    });

    $scope.cancelItem = function(item) {
      var id = item.id;
      var name = item.name;
      var action = function() {
          $('#prompt-modal').modal('hide');
          Wait('start');
          var url = path + id + '/';
          Rest.setUrl(url);
          Rest.destroy()
              .then(() => {
                  $state.go('.', null, { reload: true });
              })
              .catch(({data, status}) => {
                  toastr.error('Failed to cancel job '+name+'. GET status: ' + status, "Error!");
              });
      };

      Prompt({
          hdr: 'Delete',
          resourceName: $filter('sanitize')(name),
          body: '<div class="Prompt-bodyQuery">Are you sure you want to cancel this job ?</div>',
          action: action,
          actionText: 'Cancel'
      });
    }
  }

})();
