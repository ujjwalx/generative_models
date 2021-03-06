import tensorflow as tf
from datetime import datetime
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import os

SUMMARY_PATH = "./summaries/"
os.makedirs(SUMMARY_PATH, exist_ok=True)

IMG_DIR = './plots/'
os.makedirs(IMG_DIR, exist_ok=True)


def load_mnist_images(binarize=True):
    """
    :param binarize: Turn the images into binary vectors
    :return: x_train, x_test  Where
        x_train is a (55000 x 784) tensor of training images
        x_test is a  (10000 x 784) tensor of test images
    """
    from tensorflow.examples.tutorials.mnist import input_data
    mnist = input_data.read_data_sets("/tmp/data/", one_hot=False)
    x_train = mnist.train.images
    x_test = mnist.test.images
    if binarize:
        x_train = (x_train > 0.5).astype(x_train.dtype)
        x_test = (x_test > 0.5).astype(x_test.dtype)
    return x_train, x_test


class VariationalAutoencoder(object):

    def __init__(self, encoder_hidden_sizes, decoder_hidden_sizes, z_dim):

        self.ELBO = 0.0
        self.z_dim = z_dim
        self.batch_size = 0
        self.weight_initializer = tf.variance_scaling_initializer()
        self.encoder_dims = np.append(784, encoder_hidden_sizes)
        self.decoder_dims = np.append(self.z_dim, decoder_hidden_sizes)

        self.path = IMG_DIR + datetime.now().strftime("%Y-%m-%d %H:%M") + '/'
        os.makedirs(
            IMG_DIR + datetime.now().strftime("%Y-%m-%d %H:%M"), exist_ok=True)

    def _linear_layer(self, x, kernel_lower_dim, kernel_upper_dim, scope=None):

        with tf.variable_scope(scope or 'linear', reuse=tf.AUTO_REUSE):
            w = tf.get_variable(
                name='w',
                shape=[kernel_lower_dim, kernel_upper_dim],
                dtype=tf.float32,
                initializer=self.weight_initializer,
            )

            b = tf.get_variable(
                name='b',
                shape=[kernel_upper_dim],
                dtype=tf.float32,
                initializer=tf.constant_initializer(0.0)
            )

        return tf.add(tf.matmul(x, w), b)

    def encoder(self, x):

        layer_input = x
        last_upper_dim = 0
        self.batch_size = tf.shape(x)[0]

        for idx, (lower_dim, upper_dim) in enumerate(zip(self.encoder_dims[:-1], self.encoder_dims[1:])):
            kernel_upper_dim = upper_dim
            kernel_lower_dim = lower_dim
            layer_name = 'encoder_' + str(idx)

            layer_output = tf.nn.dropout(tf.nn.relu(self._linear_layer(
                layer_input, kernel_lower_dim, kernel_upper_dim, layer_name)), keep_prob=1)

            layer_input = layer_output
            last_upper_dim = kernel_upper_dim

        # Output for Last Layer

        enc_mu = self._linear_layer(
            layer_input, last_upper_dim, self.z_dim, 'enc_mu')
        enc_logsd = self._linear_layer(
            layer_input, last_upper_dim, self.z_dim, 'enc_logsd')

        return enc_mu, enc_logsd

    def decoder(self, z):

        layer_input = z
        last_upper_dim = 0

        for idx, (lower_dim, upper_dim) in enumerate(zip(self.decoder_dims[:-1], self.decoder_dims[1:])):
            kernel_upper_dim = upper_dim
            kernel_lower_dim = lower_dim
            layer_name = 'decoder_' + str(idx)

            layer_output = tf.nn.dropout(tf.nn.relu(self._linear_layer(
                layer_input, kernel_lower_dim, kernel_upper_dim, layer_name)), keep_prob=1)

            layer_input = layer_output
            last_upper_dim = kernel_upper_dim

        # Output for Last Layer

        dec_mu = self._linear_layer(layer_input, last_upper_dim, 784, 'dec_mu')

        return dec_mu

    def inference_network(self, x):

        enc_mu, enc_logsd = self.encoder(x)

        # Sample Epsilon. This is sampled from a standard gaussian and then multiplied with the mu and sigma
        # obtained from the encoder. Same shape as encoder-predicted standard deviation.

        epsilon = tf.random_normal(tf.shape(enc_logsd), name='epsilon')
        encoder_distrib = tf.exp(.5 * enc_logsd)

        # Sample Mu. From re-parameterization trick
        z = enc_mu + tf.multiply(encoder_distrib, epsilon)

        # Begin Decoding with sampled 'z'

        x_hat = self.decoder(z)

        KLD = -.5 * tf.reduce_sum(1. + enc_logsd - tf.pow(enc_mu, 2) -
                                  tf.exp(enc_logsd), reduction_indices=1)
        CE_loss = tf.reduce_sum(tf.nn.sigmoid_cross_entropy_with_logits(
            logits=x_hat, labels=x), reduction_indices=1)

        self.ELBO = -tf.reduce_mean(KLD + CE_loss)
        return x_hat, self.ELBO

    def train_step(self, learning_rate, lower_bound):

        train_op = tf.train.AdamOptimizer(learning_rate).minimize(-self.ELBO)
        return train_op

    def sample(self, n_samples, idx):
        """
        :param n_samples: Generate N samples from your model
        :return: A (n_samples, n_dim) array where n_dim is the dimenionality of your input
        """
        sampled_latent_variables = list()

        for n in range(n_samples):
            # Sample a random latent state
            z = tf.random_normal(shape=[1, 2])
            sampled_latent_variables.append(z)

            # Extract Bernoulli Pixel distribution for sampled latent variable.
            dec_mu = self.decoder(z)

            dist = tf.distributions.Bernoulli(probs=dec_mu)
            sample = dist.sample()
            plt.subplot(5, 4, n + 1)
            plt.text(
                0, 1, n, color='black', backgroundcolor='white', fontsize=8)
            plt.imshow(tf.reshape(sample, shape=[28, 28]).eval(), cmap='gray')
            plt.axis('off')

        # plt.savefig('./VAE_%s.png' % str(idx))
        plt.savefig(self.path + 'VAE_%s.png' % str(idx))
        plt.close()

        return

    def plot_latent_space(self, idx, minibatch_size):

        nx = ny = 20
        x_values = np.linspace(-3, 3, nx)
        y_values = np.linspace(-3, 3, ny)

        canvas = np.empty((28 * ny, 28 * nx))
        for i, yi in enumerate(x_values):
            for j, xi in enumerate(y_values):
                z_mu = np.array([[xi, yi]] * minibatch_size)
                # dist = tf.distributions.Bernoulli(logits=z_mu)
                # sample = dist.sample()
                x_mean = tf.sigmoid(self.decoder(tf.cast(z_mu, dtype=tf.float32)))
                canvas[(nx - i - 1) * 28:(nx - i) * 28, j * 28:(j + 1) * 28] = tf.reshape(x_mean[0],
                                                                                          shape=(28, 28)).eval()

        plt.figure(figsize=(8, 10))
        Xi, Yi = np.meshgrid(x_values, y_values)
        plt.imshow(canvas, origin="upper", cmap="gray")
        plt.tight_layout()
        plt.savefig('./Latent_Space_%s.png' % str(idx))
        plt.close()


def train_vae_on_mnist(z_dim=2, kernel_initializer='glorot_uniform', optimizer='adam', learning_rate=0.001, n_epochs=20,
                       test_every=1000, minibatch_size=100, encoder_hidden_sizes=[200, 200],
                       decoder_hidden_sizes=[200, 200],
                       hidden_activation='relu', plot_grid_size=10, plot_n_samples=20):
    """
    Train a variational autoencoder on MNIST and plot the results.

    :param z_dim: The dimensionality of the latent space.
    :param kernel_initializer: How to initialize the weight matrices (see tf.keras.layers.Dense)
    :param optimizer: The optimizer to use
    :param learning_rate: The learning rate for the optimizer
    :param n_epochs: Number of epochs to train
    :param test_every: Test every X training iterations
    :param minibatch_size: Number of samples per minibatch
    :param encoder_hidden_sizes: Sizes of hidden layers in encoder
    :param decoder_hidden_sizes: Sizes of hidden layers in decoder
    :param hidden_activation: Activation to use for hidden layers of encoder/decoder.
    :param plot_grid_size: Number of rows, columns to use to make grid-plot of images corresponding to latent Z-points
    :param plot_n_samples: Number of samples to draw when plotting samples from model.
    """

    # Get Data
    x_train, x_test = load_mnist_images(binarize=True)

    train_iterator = tf.data.Dataset.from_tensor_slices(
        x_train).repeat().batch(minibatch_size).make_initializable_iterator()
    n_samples, n_dims = x_train.shape
    x_minibatch = train_iterator.get_next()  # Get symbolic data, target tensors

    test_iterator = tf.data.Dataset.from_tensor_slices(x_test).repeat().batch(
        minibatch_size).make_initializable_iterator()
    x_test_minibatch = test_iterator.get_next()  # Get symbolic data, target tensors

    # Build the model
    vae = VariationalAutoencoder(encoder_hidden_sizes=encoder_hidden_sizes,
                                 decoder_hidden_sizes=decoder_hidden_sizes,
                                 z_dim=z_dim)

    # Build Graph
    train_x_hat, train_ELBO = vae.inference_network(x_minibatch)
    test_x_hat, test_ELBO = vae.inference_network(x_test_minibatch)
    train_step = vae.train_step(learning_rate, train_ELBO)


    with tf.Session() as sess:

        sess.run(train_iterator.initializer)
        sess.run(test_iterator.initializer)
        sess.run(tf.global_variables_initializer())

        # Summary Variables
        summary = tf.summary.FileWriter(SUMMARY_PATH, sess.graph)
        train_lb = tf.summary.scalar('train_ELBO', train_ELBO)
        test_lb = tf.summary.scalar('test_ELBO', test_ELBO)

        n_steps = (n_epochs * n_samples) / minibatch_size
        loss_list = list()

        for i in range(int(n_steps)):

            _, tr_loss, summary_train_lb = sess.run(
                [train_step, train_ELBO, train_lb])
            if i % test_every == 0:
                # Determine Test Loss
                te_loss = test_ELBO.eval()
                summary_test_lb = test_lb.eval()
                print("[{}] Train Step {:04d}/{:04d}, Batch Size = {}, ELBO = {} , Test Loss = {}"
                      .format(datetime.now().strftime("%Y-%m-%d %H:%M"), i + 1,
                              int(n_steps), minibatch_size, tr_loss, te_loss))

                # Sample outputs
                vae.sample(plot_n_samples, i)

            summary.add_summary(summary_train_lb, i)
            summary.add_summary(summary_test_lb, i)


        vae.plot_latent_space(i, minibatch_size)


if __name__ == '__main__':
    train_vae_on_mnist()
