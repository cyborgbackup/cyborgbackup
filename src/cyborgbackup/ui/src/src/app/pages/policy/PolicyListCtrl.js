(function () {
  'use strict';

  angular.module('CyBorgBackup.pages.policy')
    .controller('PolicyListCtrl', PolicyListCtrl);

  /** @ngInject */
  function PolicyListCtrl($scope, $filter, $uibModal, $state, $http, toastr, Prompt, Wait, Rest, ProcessErrors, GetBasePath, QuerySet) {
    $scope.tablePageSize = 10;
    let path = GetBasePath('policies');

    $scope.pipeCall = function(tableState){
      var pagination = tableState.pagination;
      var start = pagination.start || 0;
      var number = pagination.number || 25;

      QuerySet.search(path+'?page_size='+number+'&page='+((start/number)+1)).then(function(data){
         var results = data.data.results;
         tableState.pagination.numberOfPages = Math.ceil(data.data.count/tableState.pagination.number);
         $scope.policies = results;
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

    $scope.launchJob = function(item){
        var action = function() {
          $('#prompt-modal').modal('hide');
          var req = {
              method: 'POST',
              url: `${item.url}launch/`
          };

          $http(req).then((launchRes) => {
              if (!$state.includes('job')) {
                  $state.go('jobdetails', { id: launchRes.data.id }, { reload: true });
              }
          }).catch(({data, status}) => {
              toastr.error('Failed to launch job '+item.name+'. ' + data.detail, "Error!");
          });;
        };

        Prompt({
            hdr: 'Launch',
            resourceName: $filter('sanitize')(name),
            body: '<div class="Prompt-bodyQuery">Are you sure you want to launch this backup with '+item.clients.length+' clients ?</div>',
            action: action,
            actionText: 'Launch'
        });
    };

    $scope.addItem = function() {
        $state.go('policy.add');
    };

    $scope.editItem = function(item) {
        $state.go('policy.edit', { policy_id: item.id });
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

                  if($scope.policys.length === 1 && $state.params.policy_search && !_.isEmpty($state.params.policy_search.page) && $state.params.policy_search.page !== '1') {
                      reloadListStateParams = _.cloneDeep($state.params);
                      reloadListStateParams.policy_search.page = (parseInt(reloadListStateParams.policy_search.page)-1).toString();
                  }

                  if (parseInt($state.params.policy_id) === id) {
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
          body: '<div class="Prompt-bodyQuery">Are you sure you want to delete this policy ?</div>',
          action: action,
          actionText: 'Delete'
      });
    }
  }

})();
