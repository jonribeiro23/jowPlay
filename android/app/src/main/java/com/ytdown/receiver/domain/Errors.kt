package com.ytdown.receiver.domain

import java.io.IOException

/** O PC recusou o token: é preciso parear de novo. */
class NotPairedException : IOException()

/** O código de pareamento digitado está errado. */
class WrongCodeException : IOException()

/** O PC ofereceu algo que não é um áudio gerado pelo ytDown. */
class NotAudioException : IOException()
