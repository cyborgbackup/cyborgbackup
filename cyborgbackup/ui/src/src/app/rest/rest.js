(function () {
  'use strict';


let djangoSearchModel = class DjangoSearchModel {
  constructor(name, baseFields, relatedSearchFields) {
      function trimRelated(relatedSearchField){
          return relatedSearchField.replace(/\__search$/, "");
      }
      this.name = name;
      this.searchExamples = [];
      this.related = _.uniq(_.map(relatedSearchFields, trimRelated));
      // Remove "object" type fields from this list
      for (var key in baseFields) {
          if (baseFields.hasOwnProperty(key)) {
              if (baseFields[key].type === 'object'){
                  delete baseFields[key];
              }
          }
      }
      delete baseFields.url;
      this.base = baseFields;
      if(baseFields.id) {
          this.searchExamples.push("id:>10");
      }
      // Loop across the base fields and try find one of type = string and one of type = datetime
      let stringFound = false,
          dateTimeFound = false;

      _.forEach(baseFields, (value, key) => {
          if(!stringFound && value.type === 'string') {
              this.searchExamples.push(key + ":foobar");
              stringFound = true;
          }
          if(!dateTimeFound && value.type === 'datetime') {
              this.searchExamples.push(key + ":>=2000-01-01T00:00:00Z");
              this.searchExamples.push(key + ":<2000-01-01");
              dateTimeFound = true;
          }
      });
  }
  };

angular.module('CyBorgBackup.RestServices', [])
        .config(['$httpProvider', function($httpProvider) {
            $httpProvider.interceptors.push('RestInterceptor');
        }])
        .factory('Rest', ['$http', '$rootScope', '$q',
            function ($http, $rootScope, $q) {
                return {

                    headers: {},

                    setUrl: function (url) {
                        // Ensure that a trailing slash is present at the end of the url (before query params, etc)
                        this.url = url.replace(/\/?(\?|#|$)/, '/$1');
                    },
                    checkExpired: function () {
                        return ($rootScope.sessionTimer) ? $rootScope.sessionTimer.isExpired() : false;
                    },
                    pReplace: function () {
                        //in our url, replace :xx params with a value, assuming
                        //we can find it in user supplied params.
                        var key, rgx;
                        for (key in this.params) {
                            rgx = new RegExp("\\:" + key, 'gm');
                            if (rgx.test(this.url)) {
                                this.url = this.url.replace(rgx, this.params[key]);
                                delete this.params[key];
                            }
                        }
                    },
                    createResponse: function (data, status) {
                        // Simulate an http response when a token error occurs
                        // http://stackoverflow.com/questions/18243286/angularjs-promises-simulate-http-promises

                        var promise = $q.reject({
                            data: data,
                            status: status
                        });
                        promise.success = function (fn) {
                            promise.then(function (response) {
                                fn(response.data, response.status);
                            }, null);
                            return promise;
                        };
                        promise.error = function (fn) {
                            promise.then(null, function (response) {
                                fn(response.data, response.status);
                            });
                            return promise;
                        };
                        return promise;
                    },

                    setHeader: function (hdr) {
                        // Pass in { key: value } pairs to be added to the header
                        for (var h in hdr) {
                            this.headers[h] = hdr[h];
                        }
                    },
                    get: function (args) {
                        args = (args) ? args : {};
                        this.params = (args.params) ? args.params : null;
                        this.pReplace();
                        var expired = this.checkExpired();
                        if (expired) {
                            return this.createResponse({
                                detail: 'Session is expired'
                            }, 401);
                        } else {
                            return $http({
                                method: 'GET',
                                url: this.url,
                                headers: this.headers,
                                params: this.params
                            });
                        }
                    },
                    post: function (data) {
                        var expired = this.checkExpired();
                        if (expired) {
                            return this.createResponse({
                                detail: 'Session is expired'
                            }, 401);
                        } else {
                            return $http({
                                method: 'POST',
                                url: this.url,
                                headers: this.headers,
                                data: data
                            });
                        }
                    },
                    put: function (data) {
                        var expired = this.checkExpired();
                        if (expired) {
                            return this.createResponse({
                                detail: 'Session is expired'
                            }, 401);
                        } else {
                            return $http({
                                method: 'PUT',
                                url: this.url,
                                headers: this.headers,
                                data: data
                            });
                        }
                    },
                    patch: function (data) {
                        var expired = this.checkExpired();
                        if (expired) {
                            return this.createResponse({
                                detail: 'Session is expired'
                            }, 401);
                        } else {
                            return $http({
                                method: 'PATCH',
                                url: this.url,
                                headers: this.headers,
                                data: data
                            });
                        }
                    },
                    destroy: function (data) {
                        var expired = this.checkExpired();
                        if (expired) {
                            return this.createResponse({
                                detail: 'Session is expired'
                            }, 401);
                        } else {
                            return $http({
                                method: 'DELETE',
                                url: this.url,
                                headers: this.headers,
                                data: data
                            });
                        }
                    },
                    options: function (cache) {
                        var params,
                            expired = this.checkExpired();
                        if (expired) {
                            return this.createResponse({
                                detail: 'Session is expired'
                            }, 401);
                        } else {
                            params = {
                                method: 'OPTIONS',
                                url: this.url,
                                headers: this.headers,
                                data: '',
                                cache: (cache ? true : false)
                            };
                            return $http(params);
                        }
                    }
                };
            }
        ])
        .service('RestInterceptor', [ '$rootScope', '$q', '$injector',
          function ($rootScope, $q, $injector) {
              return {
                  response: function(config) {
                      if(config.headers('auth-token-timeout') !== null){
                          $rootScope.loginConfig.promise.then(function () {
                              $MilkyProvisionConfig.session_timeout = Number(config.headers('auth-token-timeout'));
                          });
                      }
                      return config;
                  },
                  responseError: function(rejection){
                      if(rejection && rejection.data && rejection.data.detail && rejection.data.detail === "Maximum per-user sessions reached"){
                          $rootScope.sessionTimer.expireSession('session_limit');
                          var state = $injector.get('$state');
                          state.go('signOut');
                          return $q.reject(rejection);
                      }
                      return $q.reject(rejection);
                  }
              };
          }]
        )
        .constant('DjangoSearchModel', djangoSearchModel)
        .service('SmartSearchService', function() {
        return {
            /**
             * For the Smart Host Filter, values with spaces are wrapped with double quotes on input.
             * To avoid having these quoted values split up and treated as terms themselves, some
             * work is done to encode quotes in quoted values and the spaces within those quoted
             * values before calling to `splitSearchIntoTerms`.
             */
            splitFilterIntoTerms (searchString) {
                if (!searchString) {
                    return null;
                }

                let groups = [];
                let quoted;

                searchString.split(' ').forEach(substring => {
                    if (/:"/g.test(substring)) {
                        if (/"$/.test(substring)) {
                            groups.push(this.encode(substring));
                        } else {
                            quoted = substring;
                        }
                    } else if (quoted) {
                        quoted += ` ${substring}`;

                        if (/"/g.test(substring)) {
                            groups.push(this.encode(quoted));
                            quoted = undefined;
                        }
                    } else {
                        groups.push(substring);
                    }
                });

                return this.splitSearchIntoTerms(groups.join(' '));
            },
            encode (string) {
                string = string.replace(/'/g, '%27');

                return string.replace(/("| )/g, match => encodeURIComponent(match));
            },
            splitSearchIntoTerms(searchString) {
                return searchString.match(/(?:[^\s"']+|"[^"]*"|'[^']*')+/g);
            },
            splitTermIntoParts(searchTerm) {
                let breakOnColon = searchTerm.match(/(?:[^:"]+|"[^"]*")+/g);

                if(breakOnColon.length > 2) {
                    // concat all the strings after the first one together
                    let stringsToJoin = breakOnColon.slice(1,breakOnColon.length);
                    return [breakOnColon[0], stringsToJoin.join(':')];
                }
                else {
                    return breakOnColon;
                }
            }
        };
    })
        .service('QuerySet', ['$q', 'Rest', 'ProcessErrors', '$rootScope', 'Wait', 'DjangoSearchModel', 'SmartSearchService',
        function($q, Rest, ProcessErrors, $rootScope, Wait, DjangoSearchModel, SmartSearchService) {
            return {
                initFieldset(path, name) {
                    let defer = $q.defer();
                    defer.resolve(this.getCommonModelOptions(path, name));
                    return defer.promise;
                },

                getCommonModelOptions(path, name) {
                    let resolve, base,
                        defer = $q.defer();

                    this.url = path;
                    resolve = this.options(path)
                        .then((res) => {
                            base = res.data.actions.GET;
                            let relatedSearchFields = res.data.related_search_fields;
                            defer.resolve({
                                models: {
                                    [name]: new DjangoSearchModel(name, base, relatedSearchFields)
                                },
                                options: res
                            });
                        });
                    return defer.promise;
                },

                replaceDefaultFlags (value) {
                    value = value.toString().replace(/__icontains_DEFAULT/g, "__icontains");
                    value = value.toString().replace(/__search_DEFAULT/g, "__search");

                    return value;
                },

                replaceEncodedTokens(value) {
                    return decodeURIComponent(value).replace(/"|'/g, "");
                },

                encodeTerms (values, key) {
                    key = this.replaceDefaultFlags(key);

                    if (!Array.isArray(values)) {
                        values = this.replaceEncodedTokens(values);

                        return `${key}=${values}`;
                    }

                    return values
                        .map(value => {
                            value = this.replaceDefaultFlags(value);
                            value = this.replaceEncodedTokens(value);

                            return `${key}=${value}`;
                        })
                        .join('&');
                },
                // encodes ui-router params from {operand__key__comparator: value} pairs to API-consumable URL
                encodeQueryset(params) {
                    if (typeof params !== 'object') {
                        return '';
                    }

                    return _.reduce(params, (result, value, key) => {
                        if (result !== '?') {
                            result += '&';
                        }

                        return result += this.encodeTerms(value, key);
                    }, '?');
                },
                // encodes a ui smart-search param to a django-friendly param
                // operand:key:comparator:value => {operand__key__comparator: value}
                encodeParam(params){
                    // Assumption here is that we have a key and a value so the length
                    // of the paramParts array will be 2.  [0] is the key and [1] the value
                    let paramParts = SmartSearchService.splitTermIntoParts(params.term);
                    let keySplit = paramParts[0].split('.');
                    let exclude = false;
                    let lessThanGreaterThan = paramParts[1].match(/^(>|<).*$/) ? true : false;
                    if(keySplit[0].match(/^-/g)) {
                        exclude = true;
                        keySplit[0] = keySplit[0].replace(/^-/, '');
                    }
                    let paramString = exclude ? "not__" : "";
                    let valueString = paramParts[1];
                    if(keySplit.length === 1) {
                        if(params.searchTerm && !lessThanGreaterThan) {
                            if(params.singleSearchParam) {
                                paramString += keySplit[0] + '__icontains';
                            }
                            else {
                                paramString += keySplit[0] + '__icontains_DEFAULT';
                            }
                        }
                        else if(params.relatedSearchTerm) {
                            if(params.singleSearchParam) {
                                paramString += keySplit[0];
                            }
                            else {
                                paramString += keySplit[0] + '__search_DEFAULT';
                            }
                        }
                        else {
                            paramString += keySplit[0];
                        }
                    }
                    else {
                        paramString += keySplit.join('__');
                    }

                    if(lessThanGreaterThan) {
                        if(paramParts[1].match(/^>=.*$/)) {
                            paramString += '__gte';
                            valueString = valueString.replace(/^(>=)/,"");
                        }
                        else if(paramParts[1].match(/^<=.*$/)) {
                            paramString += '__lte';
                            valueString = valueString.replace(/^(<=)/,"");
                        }
                        else if(paramParts[1].match(/^<.*$/)) {
                            paramString += '__lt';
                            valueString = valueString.replace(/^(<)/,"");
                        }
                        else if(paramParts[1].match(/^>.*$/)) {
                            paramString += '__gt';
                            valueString = valueString.replace(/^(>)/,"");
                        }
                    }

                    if(params.singleSearchParam) {
                        return {[params.singleSearchParam]: paramString + "=" + valueString};
                    }
                    else {
                        return {[paramString] : encodeURIComponent(valueString)};
                    }
                },
                // decodes a django queryset param into a ui smart-search tag or set of tags
                decodeParam(value, key){

                    let decodeParamString = function(searchString) {
                        if(key === 'search') {
                            // Don't include 'search:' in the search tag
                            return decodeURIComponent(`${searchString}`);
                        }
                        else {
                            key = key.toString().replace(/__icontains_DEFAULT/g, "");
                            key = key.toString().replace(/__search_DEFAULT/g, "");
                            let split = key.split('__');
                            let decodedParam = searchString;
                            let exclude = false;
                            if(key.startsWith('not__')) {
                                exclude = true;
                                split = split.splice(1, split.length);
                            }
                            if(key.endsWith('__gt')) {
                                decodedParam = '>' + decodedParam;
                                split = split.splice(0, split.length-1);
                            }
                            else if(key.endsWith('__lt')) {
                                decodedParam = '<' + decodedParam;
                                split = split.splice(0, split.length-1);
                            }
                            else if(key.endsWith('__gte')) {
                                decodedParam = '>=' + decodedParam;
                                split = split.splice(0, split.length-1);
                            }
                            else if(key.endsWith('__lte')) {
                                decodedParam = '<=' + decodedParam;
                                split = split.splice(0, split.length-1);
                            }

                            let uriDecodedParam = decodeURIComponent(decodedParam);

                            return exclude ? `-${split.join('.')}:${uriDecodedParam}` : `${split.join('.')}:${uriDecodedParam}`;
                        }
                    };

                    if (Array.isArray(value)){
                        value = _.uniq(_.flattenDeep(value));
                        return _.map(value, (item) => {
                            return decodeParamString(item);
                        });
                    }
                    else {
                        return decodeParamString(value);
                    }
                },

                // encodes a django queryset for ui-router's URLMatcherFactory
                // {operand__key__comparator: value, } => 'operand:key:comparator:value;...'
                // value.isArray expands to:
                // {operand__key__comparator: [value1, value2], } => 'operand:key:comparator:value1;operand:key:comparator:value1...'
                encodeArr(params) {
                    let url;
                    url = _.reduce(params, (result, value, key) => {
                        return result.concat(encodeUrlString(value, key));
                    }, []);

                    return url.join(';');

                    // {key:'value'} => 'key:value'
                    // {key: [value1, value2, ...]} => ['key:value1', 'key:value2']
                    function encodeUrlString(value, key){
                        if (Array.isArray(value)){
                            value = _.uniq(_.flattenDeep(value));
                            return _.map(value, (item) => {
                                return `${key}:${item}`;
                            });
                        }
                        else {
                            return `${key}:${value}`;
                        }
                    }
                },

                // decodes a django queryset for ui-router's URLMatcherFactory
                // 'operand:key:comparator:value,...' => {operand__key__comparator: value, }
                decodeArr(arr) {
                    let params = {};
                    _.forEach(arr.split(';'), (item) => {
                        let key = item.split(':')[0],
                            value = item.split(':')[1];
                        if(!params[key]){
                            params[key] = value;
                        }
                        else if (Array.isArray(params[key])){
                            params[key] = _.uniq(_.flattenDeep(params[key]));
                            params[key].push(value);
                        }
                        else {
                            params[key] = [params[key], value];
                        }
                    });
                    return params;
                },
                // REST utilities
                options(endpoint) {
                    Rest.setUrl(endpoint);
                    return Rest.options(endpoint);
                },
                search(endpoint, params) {
                    Wait('start');
                    this.url = `${endpoint}${this.encodeQueryset(params)}`;
                    Rest.setUrl(this.url);

                    return Rest.get()
                        .then(function(response) {
                            Wait('stop');

                            if (response
                                .headers('X-UI-Max-Events') !== null) {
                                response.data.maxEvents = response.
                                    headers('X-UI-Max-Events');
                            }

                            return response;
                        })
                        .catch(function(response) {
                            Wait('stop');

                            this.error(response.data, response.status);

                            throw response;
                        }.bind(this));
                },
                error(data, status) {
                    if(data && data.detail){
                        let error = typeof data.detail === "string" ? data.detail : JSON.parse(data.detail);

                        if(_.isArray(error)){
                            data.detail = error[0];
                        }
                    }
                    ProcessErrors($rootScope, data, status, null, {
                        hdr: 'Error!',
                        msg: `Invalid search term entered. GET returned: ${status}`
                    });
                },
                // Removes state definition defaults and pagination terms
                stripDefaultParams(params, defaults) {
                    if(defaults) {
                        let stripped =_.pick(params, (value, key) => {
                            // setting the default value of a term to null in a state definition is a very explicit way to ensure it will NEVER generate a search tag, even with a non-default value
                            return defaults[key] !== value && key !== 'order_by' && key !== 'page' && key !== 'page_size' && defaults[key] !== null;
                        });
                        let strippedCopy = _.cloneDeep(stripped);
                        if(_.keys(_.pick(defaults, _.keys(strippedCopy))).length > 0){
                            for (var key in strippedCopy) {
                                if (strippedCopy.hasOwnProperty(key)) {
                                    let value = strippedCopy[key];
                                    if(_.isArray(value)){
                                        let index = _.indexOf(value, defaults[key]);
                                        value = value.splice(index, 1)[0];
                                    }
                                }
                            }
                            stripped = strippedCopy;
                        }
                        return _(strippedCopy).map(this.decodeParam).flatten().value();
                    }
                    else {
                        return _(params).map(this.decodeParam).flatten().value();
                    }
                }
            };
        }
    ]);

})();
