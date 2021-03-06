# Copyright (c) 2016, Claudio Bandera
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#     * Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#     * Neither the name of the organization nor the
#       names of its contributors may be used to endorse or promote products
#       derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL <COPYRIGHT HOLDER> BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# Author: Claudio Bandera
#

from __future__ import print_function
from string import Template
import sys
import os
import re


def eprint(*args, **kwargs):
    print("************************************************", file=sys.stderr, **kwargs)
    print("Error when setting up parameter '{}':".format(args[0]), file=sys.stderr, **kwargs)
    print(*args[1:], file=sys.stderr, **kwargs)
    print("************************************************", file=sys.stderr, **kwargs)
    sys.exit(1)


# TODO add group

class ParameterGenerator(object):
    """Automatic config file and header generator"""

    def __init__(self):
        """Constructor for ParamGenerator"""
        self.enums = []
        self.parameters = []

        if len(sys.argv) != 4:
            print("Unexpected amount of args")
            sys.exit(1)
        self.dynconfpath = sys.argv[1]
        self.share_dir = sys.argv[2]
        self.cpp_gen_dir = sys.argv[3]

        self.pkgname = None
        self.nodename = None
        self.classname = None

    def add_enum(self, name, description, entry_strings, default=None):
        """
        Add an enum to dynamic reconfigure
        :param name: Name of enum parameter
        :param description: Informative documentation string
        :param entry_strings: Enum entries, must be strings! (will be numbered with increasing value)
        :param default: Default value
        :return:
        """

        entry_strings = [str(e) for e in entry_strings]  # Make sure we only get strings
        if default is None:
            default = entry_strings[0]
        else:
            default = entry_strings.index(default)
        self.add(name=name, paramtype="int", description=description, edit_method=name, default=default,
                 configurable=True)
        for e in entry_strings:
            self.add(name=name + "_" + e, paramtype="int", description="Constant for enum {}".format(name),
                     default=entry_strings.index(e), constant=True)
        self.enums.append({'name': name, 'description': description, 'values': entry_strings})

    def add(self, name, paramtype, description, level=0, edit_method='""', default=None, min=None, max=None,
            configurable=False, global_scope=False, constant=False):
        """
        Add parameters to your parameter struct. Call this method from your .params file!

        - If no default value is given, you need to specify one in your launch file
        - Global parameters, vectors, maps and constant params can not be configurable
        - Global parameters, vectors and maps can not have a default, min or max value

        :param self:
        :param name: The Name of you new parameter
        :param paramtype: The C++ type of this parameter. Can be any of ['std::string', 'int', 'bool', 'float',
        'double'] or std::vector<...> or std::map<std::string, ...>
        :param description: Choose an informative documentation string for this parameter.
        :param level: (optional) Passed to dynamic_reconfigure
        :param edit_method: (optional) Passed to dynamic_reconfigure
        :param default: (optional) default value
        :param min: (optional)
        :param max: (optional)
        :param configurable: (optional) Should this parameter be dynamic configurable
        :param global_scope: (optional) If true, parameter is searched in global ('/') namespace instead of private (
        '~') ns
        :param constant: (optional) If this is true, the parameter will not be fetched from param server,
        but the default value is kept.
        :return: None
        """
        configurable = self._make_bool(configurable)
        global_scope = self._make_bool(global_scope)
        constant = self._make_bool(constant)
        newparam = {
            'name': name,
            'type': paramtype,
            'default': default,
            'level': level,
            'edit_method': edit_method,
            'description': description,
            'min': min,
            'max': max,
            'is_vector': False,
            'is_map': False,
            'configurable': configurable,
            'constant': constant,
            'global_scope': global_scope,
        }
        self._perform_checks(newparam)
        self.parameters.append(newparam)

    def _perform_checks(self, param):
        """
        Will test some logical constraints as well as correct types.
        Throws Exception in case of error.
        :param self:
        :param param: Dictionary of one param
        :return:
        """

        if param['type'].strip() == "std::string" and (param['max'] is not None or param['min'] is not None):
            eprint(param['name'],"Max or min specified for for variable of type string")
        if (param['is_vector'] or param['is_map']) and (param['max'] or param['min'] or param['default']):
            eprint(param['name'],"Max, min and default can not be specified for variable of type %s" % param['type'])
        pattern = r'^[a-zA-Z][a-zA-Z0-9_]*$'
        if not re.match(pattern, param['name']):
            eprint(param['name'],"The name of field does not follow the ROS naming conventions, "
                                 "see http://wiki.ros.org/ROS/Patterns/Conventions")
        if param['configurable'] and (
                            param['global_scope'] or param['is_vector'] or param['is_map'] or param['constant']):
            eprint(param['name'],"Global Parameters, vectors, maps and constant params can not be declared configurable! ")
        if param['global_scope'] and param['default'] is not None:
            eprint(param['name'],"Default values for global parameters should not be specified in node! ")
        if param['constant'] and param['default'] is None:
            eprint(param['name'],"Constant parameters need a default value!")
        if param['name'] in [p['name'] for p in self.parameters]:
            eprint(param['name'],"Parameter with the same name exists already")
        if param['edit_method'] != '""':
            param['configurable'] = True

        # Check type
        in_type = param['type'].strip()
        if in_type.startswith('std::vector'):
            param['is_vector'] = True
            ptype = in_type[12:-1].strip()
            self._test_primitive_type(param['name'], ptype)
            param['type'] = 'std::vector<{}>'.format(ptype)
        elif in_type.startswith('std::map'):
            param['is_map'] = True
            ptype = in_type[9:-1].split(',')
            if len(ptype) != 2:
                eprint(param['name'],"Wrong syntax used for setting up std::map<... , ...>: You provided '%s' with "
                                "parameter %s" % in_type)
            ptype[0] = ptype[0].strip()
            ptype[1] = ptype[1].strip()
            if ptype[0] != "std::string":
                eprint(param['name'],"Can not setup map with %s as key type. Only std::map<std::string, "
                                     "...> are allowed" % ptype[0])
            self._test_primitive_type(param['name'], ptype[0])
            self._test_primitive_type(param['name'], ptype[1])
            param['type'] = 'std::map<{},{}>'.format(ptype[0], ptype[1])
        else:
            # Pytype and defaults can only be applied to primitives
            self._test_primitive_type(param['name'], in_type)
            param['pytype'] = self._pytype(in_type)

    @staticmethod
    def _pytype(drtype):
        """Convert C++ type to python type"""
        return {'std::string': "str", 'int': "int", 'double': "double", 'bool': "bool"}[drtype]

    @staticmethod
    def _test_primitive_type(name, drtype):
        """
        Test whether parameter has one of the accepted C++ types
        :param name: Parametername
        :param drtype: Typestring
        :return:
        """
        primitive_types = ['std::string', 'int', 'bool', 'float', 'double']
        if drtype not in primitive_types:
            raise TypeError("'%s' has type %s, but allowed are: %s" % (name, drtype, primitive_types))

    @staticmethod
    def _get_cvalue(param, field):
        """
        Helper function to convert strings and booleans to correct C++ syntax
        :param param:
        :return: C++ compatible representation
        """
        value = param[field]
        if param['type'] == 'std::string':
            value = '"{}"'.format(param[field])
        elif param['type'] == 'bool':
            value = str(param[field]).lower()
        return str(value)

    @staticmethod
    def _get_pyvalue(param, field):
        """
        Helper function to convert strings and booleans to correct C++ syntax
        :param param:
        :return: C++ compatible representation
        """
        value = param[field]
        if param['type'] == 'std::string':
            value = '"{}"'.format(param[field])
        elif param['type'] == 'bool':
            value = str(param[field]).capitalize()
        return str(value)

    def generate(self, pkgname, nodename, classname):
        """
        Main working Function, call this at the end of your .params file!
        :param self:
        :param pkgname: Name of the catkin package
        :param nodename: Name of the Node that will hold these params
        :param classname: This should match your file name, so that cmake will detect changes in config file.
        :return: Exit Code
        """
        self.pkgname = pkgname
        self.nodename = nodename
        self.classname = classname

        self._generatecfg()
        self._generatecpp()

        return 0

    def _generatecfg(self):
        """
        Generate .cfg file for dynamic reconfigure
        :param self:
        :return:
        """
        templatefile = os.path.join(self.dynconfpath, "templates", "ConfigType.h.template")
        with open(templatefile, 'r') as f:
            template = f.read()

        param_entries = []
        dynamic_params = [p for p in self.parameters if p["configurable"]]

        for enum in self.enums:
            param_entries.append(Template("$name = gen.enum([").substitute(name=enum['name']))
            i = 0
            for value in enum['values']:
                param_entries.append(
                    Template("    gen.const(name='$name', type='$type', value=$value, descr='$descr'),").substitute(
                        name=value, type="int", value=i, descr=""))
                i += 1
            param_entries.append(Template("    ], '$description')").substitute(description=enum["description"]))

        for param in dynamic_params:
            content_line = Template("gen.add(name = '$name', paramtype = '$paramtype', level = $level, "
                                    "description = '$description', edit_method=$edit_method").substitute(
                name=param["name"],
                paramtype=param['pytype'],
                level=param['level'],
                edit_method=param['edit_method'],
                description=param['description'])
            if param['default'] is not None:
                content_line += Template(", default=$default").substitute(default=self._get_pyvalue(param, "default"))
            if param['min'] is not None:
                content_line += Template(", min=$min").substitute(min=param['min'])
            if param['max'] is not None:
                content_line += Template(", max=$max").substitute(max=param['max'])
            content_line += ")"
            param_entries.append(content_line)

        param_entries = "\n".join(param_entries)
        template = Template(template).substitute(pkgname=self.pkgname, nodename=self.nodename,
                                                 classname=self.classname, params=param_entries)

        cfg_file = os.path.join(self.share_dir, "cfg", self.classname + ".cfg")
        try:
            if not os.path.exists(os.path.dirname(cfg_file)):
                os.makedirs(os.path.dirname(cfg_file))
        except OSError:
            # Stupid error, sometimes the directory exists anyway
            pass
        with open(cfg_file, 'w') as f:
            f.write(template)
        os.chmod(cfg_file, 509)  # entspricht 775 (octal)

    def _generatecpp(self):
        """
        Generate C++ Header file, holding the parameter struct.
        :param self:
        :return:
        """

        # Read in template file
        templatefile = os.path.join(self.dynconfpath, "templates", "Parameters.h.template")
        with open(templatefile, 'r') as f:
            template = f.read()

        param_entries = []
        debug_output = []
        from_server = []
        non_default_params = []
        from_config = []
        test_limits = []

        # Create dynamic parts of the header file for every parameter
        for param in self.parameters:
            name = param['name']

            # Adjust key for parameter server
            if param["global_scope"]:
                namespace = 'std::string("/")'
            else:
                namespace = 'privateNamespace'
            full_name = '{} + "{}"'.format(namespace, param["name"])

            # Test for default value
            if param["default"] is None:
                default = ""
                non_default_params.append(Template('      << "\t" << $namespace << "$name" << " ($type) '
                                                   '\\n"\n').substitute(
                    namespace=namespace, name=name, type=param["type"]))
            else:
                default = ', {}'.format(str(param['type']) + "{" + self._get_cvalue(param, "default") + "}")

            # Test for constant value
            if param['constant']:
                param_entries.append(Template('  static constexpr auto ${name} = $default; /*!< ${description} '
                                              '*/').substitute(type=param['type'], name=name,
                                                               description=param['description'],
                                                               default=self._get_cvalue(param, "default")))
                from_server.append(Template('    testConstParam($paramname);').substitute(paramname=full_name))
            else:
                param_entries.append(Template('  ${type} ${name}; /*!< ${description} */').substitute(
                    type=param['type'], name=name, description=param['description']))
                from_server.append(Template('    getParam($paramname, $name$default);').substitute(
                    paramname=full_name, name=name, default=default, description=param['description']))

            # Test for configurable params
            if param['configurable']:
                from_config.append(Template('    $name = config.$name;').substitute(name=name))

            # Test limits
            if param['min'] is not None:
                test_limits.append(Template('    testMin<$type>($paramname, $name, $min);').substitute(
                    paramname=full_name, name=name, min=param['min'], type=param['type']))
            if param['max'] is not None:
                test_limits.append(Template('    testMax<$type>($paramname, $name, $max);').substitute(
                    paramname=full_name, name=name, max=param['max'], type=param['type']))

            # Add debug output
            debug_output.append(Template('      << "\t" << $namespace << "$name:" << $name << '
                                         '"\\n"\n').substitute(namespace=namespace, name=name))

        param_entries = "\n".join(param_entries)
        debug_output = "".join(debug_output)
        non_default_params = "".join(non_default_params)
        from_server = "\n".join(from_server)
        from_config = "\n".join(from_config)
        test_limits = "\n".join(test_limits)

        content = Template(template).substitute(pkgname=self.pkgname, ClassName=self.classname,
                                                parameters=param_entries, fromConfig=from_config,
                                                fromParamServer=from_server, debug_output=debug_output,
                                                non_default_params=non_default_params, nodename=self.nodename,
                                                test_limits=test_limits)

        header_file = os.path.join(self.cpp_gen_dir, self.classname + "Parameters.h")
        try:
            if not os.path.exists(os.path.dirname(header_file)):
                os.makedirs(os.path.dirname(header_file))
        except OSError:
            # Stupid error, sometimes the directory exists anyway
            pass
        with open(header_file, 'w') as f:
            f.write(content)

    @staticmethod
    def _make_bool(param):
        if isinstance(param, bool):
            return param
        else:
            # Pray and hope that it is a string
            return bool(param)
