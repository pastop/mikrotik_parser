#!/path/to/virtualenvs_dir/Projects/.virtualenvs/<name_venv>/bin/python

import asyncio
import asyncssh
import configparser
from collections import OrderedDict
from async_timeout import timeout
from loguru import logger

eoip_list = []
bridge_protocol_mode_list = []
bridge_dict = []

async def send_show(host:str, username:str, password:str, commands:list):
    """Запрос по SSH

    Args:
        host (str): host
        username (str): login
        password (str): password
        commands (list): список команд

    Raises:
        TimeoutError: За значение в "async with timeout(X)" ответ получен не был
        ConnectionError: В ответ на запрос ничего не вернулось
        PermissionError: Не прошла авторизация

    Returns:
        dict: Возвращается словарь где ключем является выполняемая команда
    """
    try:
        command_result = {}
        async with timeout(13):
            async with asyncssh.connect(
                    host=host,
                    port=22,
                    username=username,
                    password=password,
                    known_hosts=None
                    ) as conn:
                for command in commands:
                    result = await conn.run(command, check=False)
                    await asyncio.sleep(1)
                    if result.stdout is None:
                        raise ConnectionError
                    else:
                        command_name = str(command)#.replace(" ","_")
                        command_result[command_name] = result.stdout
                return command_result

    except asyncio.exceptions.TimeoutError:
        print ("TimeoutError")
        pass
    except asyncssh.misc.PermissionDenied:
        print ("PermissionDenied")
        pass
        
    except Exception as exx:
        logger.exception(exx)
        raise


async def multiple_replace_(target_str, replace_values):
    """Функция замены (вместо str.replace)

    Args:
        target_str : значение, в котором выполняется замена
        replace_values : упорядоченный словарь в котором передаютсмя пары вида "что меняем / на что меняем"

    Returns:
        str: итоговое значение
    """
    # получаем заменяемое: подставляемое из словаря в цикле
    for i, j in replace_values.items():
        # меняем все target_str на подставляемое
        target_str = target_str.replace(str(i), str(j))
        # logger.info(target_str)
    return target_str

async def str_formater(data:str):
    """Функция форматирования строки

    Args:
        data (str): строка, в которой нужно заменить значения. В replace_values указано что на что нужно заменить


    Returns:
        str: истоговое значение
    """
    replace_values = OrderedDict(
            [
                ("\\",""),
                ("\r\n",""),
                (" ",";"),
                (";;;;",""),
                (";","\n"),
                ("!","#"),
                ('"',""),
            ]
        )
    return await multiple_replace_(data, replace_values)

async def parse_proplist(y_):
    """Функция извлечения значения protocol-mode

    Args:
        y_ (str): результат выполнения запроса "interface bridge print where protocol-mode=rstp"
    
    Результат сохраняется в список "bridge_protocol_mode_list" для последующего использования
    """
    for i in y_.split("\r\n\r\n"):
        tmp_dict = {}
        src_data = await str_formater(i)
        tmp_list = []
        for data in src_data.splitlines():
            if '=' in data:
                tmp_list.append(data)
        for data in tmp_list:
            tmp_dict[data.split('=')[0]]=data.split('=')[1]
        if tmp_dict is not None:
            if tmp_dict.get('name') is not None:
                if tmp_dict.get('protocol-mode') == "rstp":
                    prop = await str_formater(str(tmp_dict.get('name')))
                    bridge_protocol_mode_list.append(prop)



async def parse_eoips(y_):
    """Функция извлечения значения EOIP

    Args:
        y_ (str): результат выполнения запроса "interface eoip export compact verbose"

    Результат сохраняется в список "eoip_list" для последующего использования
    """
    config_object = configparser.ConfigParser()
    config_object.read_string(y_)
    sections=config_object.sections()
    for section in sections:
        items=config_object.items(section)
        eoip_list.append(dict(items).get('name'))
        
async def parse_bridge_port(y_):
    """Функция извлечения значения Bridge

    Args:
        y_ (str): результат выполнения запроса "interface bridge port export compact verbose"
    
    Результат сохраняется в список словарей "bridge_dict" для последующего использования
    """
    config_object = configparser.ConfigParser()
    config_object.read_string(y_)
    sections=config_object.sections()
    for section in sections:
        items=config_object.items(section)
        bridge = dict(items).get('bridge')
        interface = dict(items).get('interface')
        horizon = dict(items).get('horizon')
        bridge_dict.append(
            {
                "bridge_name": bridge,
                "bridge_interface": interface,
                "bridge_horizon": horizon,
            }
        )

async def main():
    """Запуск парсера
    В r1 указаны реквизиты доступа
    В commands список команд, которые необходимо выполнить на устройстве
    """
    r1 = {
        'host': '192.168.0.1',
        'username': 'admin',
        'password': '***',
    }
    commands = ['interface eoip export compact verbose',
                'interface bridge port export compact verbose',
                'interface bridge print where protocol-mode=rstp']

    connect_ = await send_show(**r1, commands=commands)
    if connect_ is not None:
        for comm_name,result_value in connect_.items():
            strings_ = result_value.split('add ')[1:]
            for i in strings_:
                x_= await str_formater(i)
                y_ = f"[#]\n{x_}" # приведение в "виду" conf файла, для облегчения парсинга
                if comm_name == 'interface eoip export compact verbose':
                    await parse_eoips(y_)
                if comm_name == 'interface bridge port export compact verbose':
                    await parse_bridge_port(y_)
            if comm_name == 'interface bridge print where protocol-mode=rstp':
                await parse_proplist(result_value)
    tmp_list = []
    for i in bridge_dict:
        if i.get('bridge_interface') in eoip_list:
            if i.get('bridge_horizon') != 'none':
                if i.get('bridge_name') in bridge_protocol_mode_list:
                    tmp_list.append(i.get('bridge_name'))
    if not tmp_list:
        print("Not OK")
    elif len(tmp_list) % 2 == 0:
        print ("OK")
    else:
        print("Not OK")


    
     
if __name__ == "__main__":
    asyncio.run(main())
