(function () {
    'use strict';

    angular.module('CyBorgBackup.pages.catalog')
        .controller('CatalogListCtrl', CatalogListCtrl);

    /** @ngInject */
    function CatalogListCtrl($scope, $filter, $uibModal, $state, toastr, Prompt, Wait, Rest, ProcessErrors, GetBasePath, QuerySet) {
        $scope.tablePageSize = 10;
        let path = GetBasePath('catalogs');
        $.jstree.defaults.core.themes.url = true;
        $.jstree.defaults.core.themes.dir = "assets/img/theme/vendor/jstree/dist/themes";
        var newId=1;

        $scope.lastElementSelected = null;
        $scope.basicTree;

        $scope.basicConfig = {
            core: {
                multiple: false,
                animation: true,
                check_callback: true,
                worker: true
            },
            'types': {
                'type': {
                    'icon': 'ion-settings'
                },
                'host': {
                    'icon': 'ion-cube'
                },
                'date': {
                    'icon': 'ion-clock'
                },
                'folder': {
                    'icon': 'ion-ios-folder'
                },
                'default': {
                    'icon': 'ion-document-text'
                }
            },
            'plugins': ['types'],
            'version': 1
        };

        $scope.readyTree = function(){
            if($scope.lastElementSelected) {
                var elSelected = $.jstree.reference('treeCatalog').get_node($scope.lastElementSelected, true);
                if(elSelected) {
                    elSelected.children('.jstree-anchor').focus()
                }
            }
        }

        $scope.openode = function(e, data){
            var curNode = data.node;
            var url, url_info;
            if(curNode.type == 'date'){
                function requestPages(startPath) {
                    function request(startPath, items){
                        return $.ajax({
                            //url: path+'?archive_name='+curNode.text+'&path__regex=^'+startPath+'$&order=path',
                            url: '/api/v1/escatalogs/?archive_name='+curNode.original.archive_name+'&path__regexp='+startPath+'',
                            method: 'GET'
                        }).then(function(data) {
                            items=startPath + "/[^/]*";
                            if (data.count == 0){
                                return request(startPath + "/[^/]*", items);
                            } else {
                                return(startPath);
                            }
                        });
                    }
                    return request(startPath, "[^/]*");
                }
                function checkData(){
                    return $.ajax({
                        url: '/api/v1/escatalogs/?archive_name='+curNode.original.archive_name,
                        method: 'GET'
                    }).then(function(data){
                        return data.count;
                    });
                };
                checkData().then(function(count){
                    if(count > 0 ){
                        requestPages("[^/]*").then(function(items) {
                            //var url=path+'?archive_name='+curNode.text+'&path__regex=^'+items+'$&order=path';
                            var url='/api/v1/escatalogs/?archive_name='+curNode.original.archive_name+'&path__regexp='+items+'';
                            QuerySet.search(url).then(function(data){
                                if(curNode.children.length == 0){
                                    _.forEach(data.data.results, function(v){
                                        var type;
                                        if(v.mode[0] == 'd'){
                                            type = 'folder';
                                        }else{
                                            type = 'default';
                                        }
                                        $scope.treeData.push({id: (newId++).toString(), parent: curNode.id, children: [], type: type, text: v['path']});
                                    });
                                }
                                _.forEach(curNode.parents, function(v){
                                    if(v != '#'){
                                        _.find($scope.treeData, { id : v } ).state = {opened: true};
                                    }
                                });
                                _.find($scope.treeData, { id : curNode.id } ).state = {opened: true};
                                $scope.basicConfig.version ++;
                            });
                        });
                    }else{
                        $scope.treeData.push({id: (newId++).toString(), parent: curNode.id, children: [], type: 'default', text: 'No Catalog Entry'});
                        $scope.basicConfig.version ++;
                    }
                });
                QuerySet.search(GetBasePath('jobs')+'?archive_name='+curNode.original.archive_name).then(function(data){
                    console.log(data)
                    if(data.data.count > 0){
                        $scope.currentBackup = data.data.results[0];
                    }
                });
            }else{
                var master_item = _.find($scope.treeData, { id : curNode.parents[curNode.parents.length-4] } );
                url = '/api/v1/escatalogs/?archive_name='+master_item.archive_name+'&path__regexp='+curNode.text+'/[^/]*';
                QuerySet.search('/api/v1/escatalogs/?archive_name='+master_item.archive_name+'&path='+curNode.text).then(function(data){
                    $scope.currentElement = data.data.results[0];
                });
                QuerySet.search(url).then(function(data){
                    if(curNode.children.length == 0){
                        _.forEach(data.data.results, function(v){
                            var type;
                            if(v.mode[0] == 'd'){
                                type = 'folder';
                            }else{
                                type = 'default';
                            }
                            $scope.treeData.push({id: (newId++).toString(), parent: curNode.id, children: [], type: type, text: v['path']});
                        });
                    }
                    _.forEach(curNode.parents, function(v){
                        if(v != '#'){
                            _.find($scope.treeData, { id : v } ).state = {opened: true};
                        }
                    });
                    _.find($scope.treeData, { id : curNode.id } ).state = {opened: true};
                    $scope.lastElementSelected = curNode.id;
                    $scope.basicConfig.version ++;
                });
            }
        }

        QuerySet.search('/api/v1/jobs/?fields=archive_name&not__archive_name=&archive_name__isnull=False&order=-archive_name&page_size=10000').then(function(data){
            var archives = data.data.results;
            var entries_tree = [];
            _.forEach(archives, function(archiveElement){
                var archiveNamesSplit = archiveElement['archive_name'].split('-');
                var archiveType = archiveNamesSplit[0];
                var archiveHost = archiveNamesSplit[1];
                var archiveDate = archiveNamesSplit[2] + "-" + archiveNamesSplit[3] + "-" + archiveNamesSplit[4] + "-" + archiveNamesSplit[5];
                var found = false;
                var entry = null;
                entries_tree.forEach(v => {
                  if( v['text'] == archiveType && v['type'] == 'type') {
                    found = true;
                    entry = v;
                  }
                });
                if(!found){
                  entry = {id: (newId++).toString(), 'parent': '#', 'type': 'type', children: [], 'text': archiveType};
                  entries_tree.push(entry);
                }
                var tmpId = entry['id'];
                found = false;
                entries_tree.forEach(v => {
                  if( v['text'] == archiveHost && v['type'] == 'host' && v['parentId'] == tmpId) {
                    found = true;
                    entry = v;
                  }
                });
                if(!found){
                  entry = {id: (newId++).toString(), 'parent': tmpId, 'type': 'host', children: [], 'text': archiveHost};
                  entries_tree.push(entry);
                }
                tmpId = entry['id'];
                found = false;
                entries_tree.forEach(v => {
                  if( v['text'] == archiveDate && v['type'] == 'date' && v['parentId'] == tmpId) {
                    found = true;
                    entry = v;
                  }
                });
                if(!found){
                  entry = {id: (newId++).toString(), 'parent': tmpId, 'type': 'date', children: [], 'text': archiveDate, 'archive_name': archiveElement['archive_name']};
                  entries_tree.push(entry);
                }
            })
            $scope.treeData = entries_tree;
        });

    }

})();