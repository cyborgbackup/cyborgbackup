(function () {
  'use strict';

  angular.module('CyBorgBackup.pages.profile')
    .controller('ProfilePageCtrl', ProfilePageCtrl);

  /** @ngInject */
  function ProfilePageCtrl($scope, $rootScope, fileReader, $filter, $uibModal, baAuthentication) {
    $scope.picture = $filter('appImage')('theme/no-photo.png');
    $scope.user = $rootScope.current_user;

    $scope.removePicture = function () {
      $scope.picture = $filter('appImage')('theme/no-photo.png');
      $scope.noPicture = true;
    };

    $scope.uploadPicture = function () {
      var fileInput = document.getElementById('uploadFile');
      fileInput.click();

    };

    $scope.unconnect = function (item) {
      item.href = undefined;
    };

    $scope.showModal = function (item) {
      $uibModal.open({
        animation: false,
        controller: 'ProfileModalCtrl',
        templateUrl: 'app/pages/profile/profileModal.html'
      }).result.then(function (link) {
          item.href = link;
        });
    };

    $scope.getFile = function () {
      fileReader.readAsDataUrl($scope.file, $scope)
          .then(function (result) {
            $scope.picture = result;
          });
    };

    $scope.switches = [true, true, false, true, true, false];
  }

})();
