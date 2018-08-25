import random

from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from django_redis import get_redis_connection

from verifications import constants
from meiduo_mall.libs.yuntongxun.sms import CCP

# Create your views here.

# 获取logger
import logging

logger = logging.getLogger('django')


# GET /sms_codes/(?P<mobile>1[3-9]\d{9})/
class SMSCodeView(APIView):
    def get(self, request, mobile):
        """
        获取短信验证码:
        1. 生成短信验证码内容
        2. 在redis中保存短信验证码内容，以`mobile`为key，以短信验证码内容为value
        3. 使用云通讯发送短信验证码
        4. 返回应答，发送短信成功
        """
        # 判断60s之内是否给`mobile`发送过短信
        redis_conn = get_redis_connection('verify_codes')
        send_flag = redis_conn.get('send_flag_%s' % mobile)

        if send_flag:
            return Response({'message': '发送短信过于频繁'}, status=status.HTTP_400_BAD_REQUEST)

        # 1. 生成短信验证码内容，随机生成一个6位数字
        sms_code = '%06d' % random.randint(0, 999999)

        # 2. 在redis中保存短信验证码内容，以`mobile`为key，以短信验证码内容为value
        # redis_conn.set('<key>', '<value>', '<expires>')
        # redis_conn.setex('<key>', '<expires>', '<value>')

        # redis管道：可以向管道中添加多个要执行redis命令，然后一次性执行
        pl = redis_conn.pipeline()

        # 向管道添加命令
        pl.setex('sms_%s' % mobile, constants.SMS_CODE_REDIS_EXPIRES, sms_code)
        # 设置一个给`mobile`发送短信的标记
        pl.setex('send_flag_%s' % mobile, constants.SEND_SMS_CODE_INTERVAL, 1)

        # 执行管道中的命令
        pl.execute()

        # 3. 使用云通讯发送短信验证码
        expires = constants.SMS_CODE_REDIS_EXPIRES // 60
        try:
            res = CCP().send_template_sms(mobile, [sms_code, expires], constants.SMS_CODE_TEMP_ID)
        except Exception as e:
            logger.error('mobile: %s，发送短信异常' % mobile)
            return Response({'message': '发送短信异常'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        if res != 0:
            # 发送短信失败
            return Response({'message': '发送短信异常'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        # # 发出发送短信任务
        # from celery_tasks.sms.tasks import send_sms_code
        # send_sms_code.delay(mobile, sms_code, expires)

        # 4. 返回应答，发送短信成功
        return Response({'message': 'OK'})
