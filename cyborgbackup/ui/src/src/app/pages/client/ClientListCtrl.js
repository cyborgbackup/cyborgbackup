(function () {
  'use strict';

  angular.module('CyBorgBackup.pages.client')
    .controller('ClientListCtrl', ClientListCtrl);

  /** @ngInject */
  function ClientListCtrl($scope, $filter, $uibModal, $state, toastr, Prompt, Wait, Rest, ProcessErrors, GetBasePath, QuerySet) {
    $scope.tablePageSize = 10;
    let path = GetBasePath('clients');

    $scope.pipeCall = function(tableState){
      var pagination = tableState.pagination;
      var start = pagination.start || 0;
      var number = pagination.number || 25;

      QuerySet.search(path+'?page_size='+number+'&page='+((start/number)+1)).then(function(data){
         var results = data.data.results;
         tableState.pagination.numberOfPages = Math.ceil(data.data.count/tableState.pagination.number);
         $scope.clients = results;
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
        $state.go('client.add');
    };

    $scope.editItem = function(item) {
        $state.go('client.edit', { client_id: item.id });
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

                  if($scope.clients.length === 1 && $state.params.client_search && !_.isEmpty($state.params.client_search.page) && $state.params.client_search.page !== '1') {
                      reloadListStateParams = _.cloneDeep($state.params);
                      reloadListStateParams.client_search.page = (parseInt(reloadListStateParams.client_search.page)-1).toString();
                  }

                  if (parseInt($state.params.client_id) === id) {
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
          body: '<div class="Prompt-bodyQuery">Are you sure you want to delete this client ?</div>',
          action: action,
          actionText: 'Delete'
      });
    }
  }

})();
