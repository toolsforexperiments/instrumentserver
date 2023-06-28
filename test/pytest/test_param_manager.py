import json

from instrumentserver.params import ParameterManager


def prep_param_manager(params, template=1):
    if template == 1:
        params.add_parameter(name='my_param', initial_value=123, unit='M')
        params.add_parameter(name='nested_param.child1', initial_value=456, unit='a')
        params.add_parameter(name='nested_param.child2', initial_value=789, unit='b')
        params.add_parameter(name='nested_param.how.are.you', initial_value=111, unit='b')
        params.add_parameter(name='nested_param.how.are.too', initial_value=222, unit='b')
    elif template == 2:
        params.add_parameter(name='his_param', initial_value=-123, unit='n')
        params.add_parameter(name='nested_param.son1', initial_value=-456, unit='c')
        params.add_parameter(name='nested_param.son2', initial_value=-789, unit='d')
    elif template == 3:
        params.add_parameter(name='her_param', initial_value=0, unit='p')
        params.add_parameter(name='nested_param.daughter1', initial_value=1, unit='e')
        params.add_parameter(name='nested_param.daughter2', initial_value=2, unit='f')
    elif template == 4:
        params.add_parameter(name='our_param', initial_value=3, unit='m')
        params.add_parameter(name='nested_param.sibling1', initial_value=[4, 6], unit='g')
        params.nested_param.sibling1(1234856834)
        params.add_parameter(name='nested_param.sibling2', initial_value=[5, 7], unit='h')


def test_param(param_manager):
    cli, params = param_manager

    params.add_parameter(name='my_param', initial_value=123, unit='M')
    assert params.my_param() == 123
    assert params.my_param.unit == 'M'

    params.my_param(456)
    assert params.my_param() == 456


def test_removing_all_params():
    params = ParameterManager(name='params')

    prep_param_manager(params)
    prep_param_manager(params, template=2)
    prep_param_manager(params, template=3)
    prep_param_manager(params, template=4)

    params.remove_all_parameters()

    assert params.list() == []


def test_finding_all_profiles(tmp_path):
    params = ParameterManager(name='params')

    prep_param_manager(params)
    params.toFile(tmp_path, 'first')

    prep_param_manager(params, template=2)
    params.toFile(tmp_path, 'second')

    prep_param_manager(params, template=3)
    params.toFile(tmp_path, 'third')

    prep_param_manager(params, template=4)
    params.toFile(tmp_path, 'fourth')

    params.workingDirectory = tmp_path
    profiles = params.refresh_profiles()

    assert sorted(profiles) == sorted(['parameter_manager-first.json',
                                       'parameter_manager-second.json',
                                       'parameter_manager-third.json',
                                       'parameter_manager-fourth.json'])


def test_saving_correct_profile(tmp_path):

    params = ParameterManager(name='params')
    params.workingDirectory = tmp_path

    prep_param_manager(params)
    params.toFile(name='first')
    file_path = tmp_path.joinpath('parameter_manager-first.json')
    assert file_path.exists()

    params.my_param(8888)
    params.toFile()

    with open(file_path) as file:
        data = json.load(file)

    assert data['params.my_param']['value'] == 8888


def test_loading_correct_profile(tmp_path):

    params = ParameterManager(name='params')
    params.workingDirectory = tmp_path

    prep_param_manager(params)
    params.toFile(name='first')
    file_path = tmp_path.joinpath('parameter_manager-first.json')

    with open(file_path) as file:
        data = json.load(file)

    data['params.my_param']['value'] = 9999

    with open(file_path, 'w') as file:
        json.dump(data, file)

    params.fromFile()
    assert params.my_param() == 9999


def prep_switching_profiles(tmp_path):
    params = ParameterManager(name='params')

    prep_param_manager(params)
    params.toFile(tmp_path, 'first')

    params.remove_all_parameters()

    prep_param_manager(params, template=2)
    params.toFile(tmp_path, 'second')

    params.workingDirectory = tmp_path
    params.refresh_profiles()

    return params


def test_switching_profiles(tmp_path):

    params = prep_switching_profiles(tmp_path)

    params.switch_to_profile('parameter_manager-first.json')

    assert params.my_param() == 123
    assert params.nested_param.child1() == 456
    assert params.nested_param.child2() == 789


def test_switching_profiles_short_name(tmp_path):
    params = prep_switching_profiles(tmp_path)

    params.switch_to_profile('first')

    assert params.my_param() == 123
    assert params.nested_param.child1() == 456
    assert params.nested_param.child2() == 789

    params.switch_to_profile('second')

    assert params.his_param() == -123
    assert params.nested_param.son1() == -456
    assert params.nested_param.son2() == -789


def test_switching_profiles_automatic_save(tmp_path):
    params = prep_switching_profiles(tmp_path)

    params.his_param(111)
    params.nested_param.son1(222)
    params.nested_param.son2(333)

    params.switch_to_profile('first')

    # Open the JSON file
    with open(tmp_path.joinpath('parameter_manager-second.json')) as file:
        # Load the JSON data
        second = json.load(file)

    assert second['params.his_param']['value'] == 111
    assert second['params.nested_param.son1']['value'] == 222
    assert second['params.nested_param.son2']['value'] == 333


def test_selectedProfile_only_changing_when_correct_name(tmp_path):
    params = ParameterManager(name='params')

    prep_param_manager(params)
    names_path = tmp_path.joinpath('names.json')
    params.toFile(names_path)

    assert params.selectedProfile == 'parameter_manager-params.json'

    params.fromFile(names_path)
    assert params.selectedProfile == 'parameter_manager-params.json'

    params.toFile(tmp_path, 'params')
    assert params.selectedProfile == 'parameter_manager-params.json'

    new_path = names_path.replace(tmp_path.joinpath('parameter_manager-names.json'))
    params.fromFile(new_path)
    assert params.selectedProfile == 'parameter_manager-names.json'

