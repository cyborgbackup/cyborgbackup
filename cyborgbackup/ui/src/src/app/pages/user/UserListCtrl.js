(function () {
  'use strict';

  angular.module('CyBorgBackup.pages.user')
    .controller('UserListCtrl', UserListCtrl);

  /** @ngInject */
  function UserListCtrl($rootScope, $scope, $filter, $uibModal, $state, toastr, Prompt, Wait, Rest, ProcessErrors, GetBasePath, QuerySet) {
    $scope.tablePageSize = 10;
    let path = GetBasePath('users');

    $scope.pipeCall = function(tableState){
      var pagination = tableState.pagination;
      var start = pagination.start || 0;
      var number = pagination.number || 25;

      QuerySet.search(path+'?page_size='+number+'&page='+((start/number)+1)).then(function(data){
         var results = data.data.results;
         tableState.pagination.numberOfPages = Math.ceil(data.data.count/tableState.pagination.number);
         $scope.users = results;
      });
    };

    $scope.current_user_email = $rootScope.current_user.email;

    $scope.addItem = function() {
        $state.go('user.add');
    };

    $scope.editItem = function(item) {
      if($rootScope.current_user.email == item.email)
      {
        $state.go('profile');
      }else{
        $state.go('user.edit', { user_id: item.id });
      }
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

                  if($scope.users.length === 1 && $state.params.user_search && !_.isEmpty($state.params.user_search.page) && $state.params.user_search.page !== '1') {
                      reloadListStateParams = _.cloneDeep($state.params);
                      reloadListStateParams.user_search.page = (parseInt(reloadListStateParams.user_search.page)-1).toString();
                  }

                  if (parseInt($state.params.user_id) === id) {
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
          body: '<div class="Prompt-bodyQuery">Are you sure you want to delete this user ?</div>',
          action: action,
          actionText: 'Delete'
      });
    }
  }

})();
