(function () {
  'use strict';

  angular.module('CyBorgBackup.pages.dashboard')
      .directive('dashboardSummary', dashboardSummary);

  /** @ngInject */
  function dashboardSummary() {
    return {
      restrict: 'E',
      controller: 'DashboardSummaryCtrl',
      templateUrl: 'app/pages/dashboard/dashboardSummary/dashboardSummary.html'
    };
  }
})();
