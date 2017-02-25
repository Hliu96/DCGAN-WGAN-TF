# -*- coding: utf-8 -*-
"""
Created on Mon Feb 20 17:44:01 2017

@author: fankai
"""

import tensorflow as tf
import tensorflow.contrib.layers as tcl
import numpy as np
import os

from ops import deconv2d, conv2d, lrelu
from lsun_batch import batched_images
    
    
def ganloss(yl, c=0.99):
    return tf.reduce_mean(tf.nn.sigmoid_cross_entropy_with_logits(yl, c*tf.ones_like(yl)))

        
class DCGAN(object):
    
    def __init__(self, img_shape, train_mode=True, model_path=None, 
                 latent_dim=100,
                 batch_size=64, d_learning_rate=1e-4, g_learning_rate=3e-4, eps=1e-8, 
                 grad_clip='Norm',
                 Wloss=False, Bn=True, Adam=True
                 ):
                     
        self.img_shape = img_shape
        self.train_mode = train_mode
        self.model_path = model_path
        
        self.H = img_shape[0]
        self.W = img_shape[1]
        self.C = img_shape[2]

        self.z_size = latent_dim        
        self.batch_size = batch_size
        
        self.Wloss = Wloss
        self.Bn = Bn
          
        # build model
        self.DO_SHARE = None
        self.x_r = tf.placeholder(tf.float32, shape=[self.batch_size] + list(self.img_shape))
                
#        z = tf.random_normal((self.batch_size, 1, 1, self.z_size), 0, 1)
        z = tf.random_uniform((self.batch_size, 1, 1, self.z_size), -1, 1)
        self.x_g = self.generator(z)       
        
        if self.Bn:               
            yl_r = self.discriminator(self.x_r)
            self.DO_SHARE = True
            yl_g = self.discriminator(self.x_g)
        else:
            x = tf.concat(0, [self.x_r, self.x_g])
            yl = self.discriminator(x)
            yl_r, yl_g = tf.split(0, 2, yl)        
        
        if Wloss:
            self.d_loss = tf.reduce_mean(yl_r - yl_g, axis=0)
            self.g_loss = tf.reduce_mean(yl_g, axis=0)
        else: # Vanilla GAN loss
            self.d_loss = ganloss(yl_r) + ganloss(yl_g, 0.01)
            self.g_loss = ganloss(yl_g)
                    
        t_vars = tf.trainable_variables()
        
        self.d_vars = [var for var in t_vars if 'd_' in var.name]
        self.g_vars = [var for var in t_vars if 'g_' in var.name]
        
        if Adam:
            self.d_optimizer = tf.train.AdamOptimizer(d_learning_rate, beta1=0.5, beta2=0.999)
            d_grads = self.d_optimizer.compute_gradients(self.d_loss, self.d_vars)
            clip_d_grads = [(tf.clip_by_norm(grad, 5), var) for grad, var in d_grads if grad is not None]
            self.d_optimizer = self.d_optimizer.apply_gradients(clip_d_grads)
            
            self.g_optimizer = tf.train.AdamOptimizer(g_learning_rate, beta1=0.5, beta2=0.999)
            g_grads = self.g_optimizer.compute_gradients(self.g_loss, self.g_vars)
            clip_g_grads = [(tf.clip_by_norm(grad, 5), var) for grad, var in g_grads if grad is not None]
            self.g_optimizer = self.g_optimizer.apply_gradients(clip_g_grads)
        else:
            self.d_optimizer = tf.train.RMSPropOptimizer(d_learning_rate, decay=0.99, epsilon=eps)
            d_grads = self.d_optimizer.compute_gradients(self.d_loss, self.d_vars)
            #clip_d_grads = [(tf.clip_by_norm(grad, 5), var) for grad, var in d_grads if grad is not None]
            clip_d_grads = [(grad, var) for grad, var in d_grads if grad is not None]
            self.d_optimizer = self.d_optimizer.apply_gradients(clip_d_grads)
            
            self.d_clip = [tf.assign(var, tf.clip_by_value(var, -0.01, 0.01)) for var in self.d_vars]
            
            self.g_optimizer = tf.train.RMSPropOptimizer(g_learning_rate, decay=0.99, epsilon=eps)
            g_grads = self.g_optimizer.compute_gradients(self.g_loss, self.g_vars)
            #clip_g_grads = [(tf.clip_by_norm(grad, 5), var) for grad, var in g_grads if grad is not None]
            clip_g_grads = [(grad, var) for grad, var in g_grads if grad is not None]
            self.g_optimizer = self.g_optimizer.apply_gradients(clip_g_grads)                
        
    
    def train(self, max_epoch=10, K=5):
        
        with tf.Session() as sess:
            
            saver = tf.train.Saver()
            sess.run(tf.global_variables_initializer())     
                        
            k = 0
            for epoch in range(max_epoch):
                
                START_IDX = 0
                for next_idx, xtrain in batched_images(START_IDX, self.batch_size):
                    START_IDX = next_idx
                    
#                for batch_lines in iterate_minibatches_u(datanames, self.batch_size, shuffle=True):
#                    xtrain = [ scipy.misc.imread(batch_name) for batch_name in batch_lines ]
#                    xtrain = np.array(xtrain).astype(np.float32) / 127.5 - 1 # batch_size x H x W x C
#                    #xtrain = np.expand_dims(xtrain, -1) # if xtrain is bs x H x W
                    
                    if self.Wloss:
                        sess.run(self.d_clip)
                        
                    _, Ld = sess.run([self.d_optimizer, self.d_loss],feed_dict={self.x_r: xtrain})
                    k += 1
                    
                    if self.Wloss:                    
                        if k < 2500 or k % 2500 <= 100:
                            GK = 100
                        else:
                            GK = K
    
                        if (k % GK) == 0:
                            _, Lg = sess.run([self.g_optimizer, self.g_loss],feed_dict={self.x_r: xtrain})

                    else:
                        _, Lg = sess.run([self.g_optimizer, self.g_loss],feed_dict={self.x_r: xtrain})

                    if k % 1000 == 0:
                        print("Epoch=%d: Ld: %f Lg: %f" % (epoch, Ld, Lg))
                
                        xshow = self.get_showimages(sess)
                        out_file = os.path.join("output_dcgan","dcgan_"+str(int(k/10000))+".npy")
                        np.save(out_file, xshow)
                        
                self.save_model(saver, sess, step=epoch)
                
            xshow = self.get_showimages(sess, self.batch_size)
            out_file = os.path.join("output_dcgan","dcgan_end.npy")
            np.save(out_file, xshow)
 
           
    def save_model(self, saver, sess, step):
        """
        save model with path error checking
        """
        if self.model_path is None:
            my_path = "model/myckpt" # default path in tensorflow saveV2 format
            # try to make directory
            if not os.path.exists("model"):
                try:
                    os.makedirs("model")
                except OSError as e:
                    if e.errno != errno.EEXIST:
                        raise
        else: 
            my_path = self.model_path
                
        saver.save(sess, my_path, global_step=step)
        
    
    def get_showimages(self, sess, n = 8):
        num_show = min(n*n, self.batch_size)
        xg = sess.run(self.x_g) # batch_size x H x W x C
        xshow_ = np.array(xg)[:num_show,:,:,:] # num_show x H x W x C
#        xshow_ = np.reshape(xshow_, [n, n, self.H, self.W, self.C])
#        xshow = 0.5*(xshow+1.0)        
#        xshow = np.transpose(xshow_, [1,2,0,3,4]) # n x H x n x W x C
#        return xshow.reshape([-1,n*self.W, self.C]) if self.C > 1 else xshow.reshape([-1,n*self.W])
        return 0.5*(xshow_+1.0)
        
    
    def generator(self, z):
        with tf.variable_scope("g_deconv0",reuse=None):
            deconv0 = deconv2d(z, [self.batch_size, 4, 4, 1024], 4, 4, 1, 1, bias=not self.Bn, padding='VALID')
            deconv0 = tf.nn.relu(tcl.batch_norm(deconv0)) if self.Bn else tf.nn.relu(deconv0)
        with tf.variable_scope("g_deconv1",reuse=None):
            deconv1 = deconv2d(deconv0, [self.batch_size, 8, 8, 512], 5, 5, 2, 2, bias=not self.Bn, padding='SAME')
            deconv1 = tf.nn.relu(tcl.batch_norm(deconv1)) if self.Bn else tf.nn.relu(deconv1)
        with tf.variable_scope("g_deconv2",reuse=None):
            deconv2 = deconv2d(deconv1, [self.batch_size, 16, 16, 256], 5, 5, 2, 2, bias=not self.Bn, padding='SAME')
            deconv2 = tf.nn.relu(tcl.batch_norm(deconv2)) if self.Bn else tf.nn.relu(deconv2)
        with tf.variable_scope("g_deconv3",reuse=None):
            deconv3 = deconv2d(deconv2, [self.batch_size, 32, 32, 128], 5, 5, 2, 2, bias=not self.Bn, padding='SAME')
            deconv3 = tf.nn.relu(tcl.batch_norm(deconv3)) if self.Bn else tf.nn.relu(deconv3)
        with tf.variable_scope("g_deconv4",reuse=None):
            deconv4 = deconv2d(deconv3, [self.batch_size, 64, 64, 3], 5, 5, 2, 2, bias=not self.Bn, padding='SAME')
        return tf.tanh(deconv4)
    
    
    def discriminator(self, x, Cc=128):
        with tf.variable_scope("d_conv1",reuse=self.DO_SHARE):
            conv1 = conv2d(x, self.C, Cc, 5, 5, 2, 2, bias=not self.Bn, padding='SAME') # H/2 x W/2
            conv1 = lrelu(conv1)
        with tf.variable_scope("d_conv2",reuse=self.DO_SHARE):
            conv2 = conv2d(conv1, Cc, 2*Cc, 5, 5, 2, 2, bias=not self.Bn, padding='SAME') # H/4 x W/4
            conv2 = lrelu(tcl.batch_norm(conv2)) if self.Bn else lrelu(conv2)
        with tf.variable_scope("d_conv3",reuse=self.DO_SHARE):
            conv3 = conv2d(conv2, 2*Cc, 4*Cc, 5, 5, 2, 2, bias=not self.Bn, padding='SAME') # H/8 x W/8
            conv3 = lrelu(tcl.batch_norm(conv3)) if self.Bn else lrelu(conv3)
        with tf.variable_scope("d_conv4",reuse=self.DO_SHARE):
            conv4 = conv2d(conv3, 4*Cc, 8*Cc, 5, 5, 2, 2, bias=not self.Bn, padding='SAME') # H/16 x W/16
            conv4 = lrelu(tcl.batch_norm(conv4)) if self.Bn else lrelu(conv4)
        with tf.variable_scope("d_conv5",reuse=self.DO_SHARE):
            yl_f = conv2d(conv4, 8*Cc, 1, 4, 4, 1, 1, bias=not self.Bn, padding='VALID')
        return tf.reshape(yl_f, [-1, 1])
        

if __name__ == "__main__":
    
    mymodel = DCGAN(img_shape=[64, 64, 3], train_mode=True, model_path="model/dcganlsun")
    mymodel.train(max_epoch=3, K=5)
